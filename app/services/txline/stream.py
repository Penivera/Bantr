import json
import asyncio
import httpx
from typing import AsyncIterator, Callable, Any
from dataclasses import dataclass, field
from app.core.config import settings
from app.core.constants import (
    STAT_KEY_GOAL_P1, STAT_KEY_GOAL_P2,
    STAT_KEY_YELLOW_P1, STAT_KEY_YELLOW_P2,
    STAT_KEY_RED_P1, STAT_KEY_RED_P2,
    STAT_KEY_CORNER_P1, STAT_KEY_CORNER_P2,
    BET_STATUS_OPEN, BET_STATUS_CALLED, BET_STATUS_FUNDED,
    BET_STATUS_RESOLVED, BET_STATUS_VOID,
)
from app.core.logging import get_logger
from app.services.txline.auth import TxLineCredentials

logger = get_logger(__name__)


@dataclass
class SseMessage:
    id: str | None = None
    event: str | None = None
    data: str = ""
    retry: int | None = None


@dataclass
class ScoreEventRaw:
    fixture_id: str = ""
    action: str | None = None
    seq: int | None = None
    ts: int | None = None
    period: str | None = None
    phase: int | None = None
    status_id: int | None = None
    game_state: str | None = None
    stats: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchEvent:
    fixture_id: str
    type: str  # "goal" | "card" | "corner" | "score_update"
    team: str | None = None
    timestamp: int = 0
    raw: ScoreEventRaw | None = None


def parse_sse_block(block: str) -> SseMessage | None:
    msg = SseMessage()
    for line in block.split("\n"):
        line = line.rstrip("\r")
        if not line or line.startswith(":"):
            continue
        sep = line.find(":")
        field = line[:sep] if sep != -1 else line
        value = line[sep + 1:].lstrip(" ") if sep != -1 else ""
        if field == "data":
            msg.data += value + "\n"
        elif field == "event":
            msg.event = value
        elif field == "id":
            msg.id = value
        elif field == "retry":
            msg.retry = int(value)
    msg.data = msg.data.rstrip("\n")
    return msg if msg.data or msg.event or msg.id else None


def detect_delta(
    prev_stats: dict[str, int],
    curr_stats: dict[str, int],
) -> dict:
    def g(key: int) -> int:
        return curr_stats.get(str(key), 0)

    def pg(key: int) -> int:
        return prev_stats.get(str(key), 0)

    goals_changed = g(STAT_KEY_GOAL_P1) != pg(STAT_KEY_GOAL_P1) or g(STAT_KEY_GOAL_P2) != pg(STAT_KEY_GOAL_P2)
    cards_changed = (
        g(STAT_KEY_YELLOW_P1) != pg(STAT_KEY_YELLOW_P1)
        or g(STAT_KEY_YELLOW_P2) != pg(STAT_KEY_YELLOW_P2)
        or g(STAT_KEY_RED_P1) != pg(STAT_KEY_RED_P1)
        or g(STAT_KEY_RED_P2) != pg(STAT_KEY_RED_P2)
    )
    corners_changed = g(STAT_KEY_CORNER_P1) != pg(STAT_KEY_CORNER_P1) or g(STAT_KEY_CORNER_P2) != pg(STAT_KEY_CORNER_P2)

    return {
        "changed": goals_changed or cards_changed or corners_changed,
        "goals_changed": goals_changed,
        "cards_changed": cards_changed,
        "corners_changed": corners_changed,
        "goals": {"p1": g(STAT_KEY_GOAL_P1), "p2": g(STAT_KEY_GOAL_P2)},
        "cards": {"p1": g(STAT_KEY_YELLOW_P1) + g(STAT_KEY_RED_P1), "p2": g(STAT_KEY_YELLOW_P2) + g(STAT_KEY_RED_P2)},
        "corners": {"p1": g(STAT_KEY_CORNER_P1), "p2": g(STAT_KEY_CORNER_P2)},
    }


def normalize_event(raw: ScoreEventRaw, prev_stats: dict[str, int] | None = None) -> MatchEvent | None:
    fid = str(raw.fixture_id)
    prev = prev_stats or {}
    stats = raw.stats or {}

    if raw.action == "game_finalised":
        return MatchEvent(fixture_id=fid, type="score_update", timestamp=raw.ts or 0, raw=raw)

    if not stats:
        return MatchEvent(fixture_id=fid, type="score_update", timestamp=raw.ts or 0, raw=raw)

    delta = detect_delta(prev, stats)
    if not delta["changed"]:
        return MatchEvent(fixture_id=fid, type="score_update", timestamp=raw.ts or 0, raw=raw)

    event_type = "score_update"
    team = None

    if delta["goals_changed"]:
        event_type = "goal"
        team = "team_1" if stats.get(str(STAT_KEY_GOAL_P1), 0) != prev.get(str(STAT_KEY_GOAL_P1), 0) else "team_2"
    elif delta["cards_changed"]:
        event_type = "card"
        p1_current = stats.get(str(STAT_KEY_YELLOW_P1), 0) + stats.get(str(STAT_KEY_RED_P1), 0)
        p1_prev = prev.get(str(STAT_KEY_YELLOW_P1), 0) + prev.get(str(STAT_KEY_RED_P1), 0)
        team = "team_1" if p1_current != p1_prev else "team_2"
    elif delta["corners_changed"]:
        event_type = "corner"
        team = "team_1" if stats.get(str(STAT_KEY_CORNER_P1), 0) != prev.get(str(STAT_KEY_CORNER_P1), 0) else "team_2"

    return MatchEvent(fixture_id=fid, type=event_type, team=team, timestamp=raw.ts or 0, raw=raw)


class TxLineStreamClient:
    def __init__(self, credentials: TxLineCredentials):
        self.credentials = credentials
        self.listeners: dict[str, list[Callable[[MatchEvent], None]]] = {}
        self.last_stats: dict[str, dict[str, int]] = {}
        self._running = False
        self._abort = asyncio.Event()

    def on_match_event(self, fixture_id: str, cb: Callable[[MatchEvent], None]) -> None:
        self.listeners.setdefault(fixture_id, []).append(cb)

    async def start(self) -> None:
        self._running = True
        api_base = f"{settings.txline_api_origin}/api"
        stream_url = f"{api_base}/scores/stream"

        while self._running and not self._abort.is_set():
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream(
                        "GET", stream_url,
                        headers={
                            "Authorization": f"Bearer {self.credentials.jwt}",
                            "X-Api-Token": self.credentials.api_token,
                            "Accept": "text/event-stream",
                            "Cache-Control": "no-cache",
                        }
                    ) as response:
                        if response.status_code in (401, 403):
                            logger.warning("stream_auth_failed", status=response.status_code)
                            await asyncio.sleep(3)
                            continue
                        if response.status_code != 200:
                            logger.error("stream_failed", status=response.status_code)
                            break

                        logger.info("stream_connected")
                        buffer = ""
                        async for chunk in response.aiter_bytes():
                            if self._abort.is_set():
                                break
                            buffer += chunk.decode("utf-8", errors="replace")
                            while "\n\n" in buffer:
                                block, buffer = buffer.split("\n\n", 1)
                                sse_msg = parse_sse_block(block)
                                if sse_msg and sse_msg.data:
                                    try:
                                        payload = json.loads(sse_msg.data)
                                        await self._handle_payload(payload)
                                    except json.JSONDecodeError:
                                        pass
            except (httpx.ReadError, httpx.ConnectError, httpx.RemoteProtocolError) as e:
                logger.warning("stream_disconnected", error=str(e))
                await asyncio.sleep(3)
            except Exception as e:
                logger.error("stream_error", error=str(e))
                await asyncio.sleep(3)

    async def _handle_payload(self, payload: dict) -> None:
        raw = ScoreEventRaw(
            fixture_id=str(payload.get("fixtureId", payload.get("fixture_id", ""))),
            action=payload.get("action"),
            seq=payload.get("seq") or payload.get("Seq"),
            ts=payload.get("ts") or payload.get("Ts"),
            period=payload.get("period"),
            phase=payload.get("phase"),
            status_id=payload.get("statusId"),
            game_state=payload.get("gameState"),
            stats=payload.get("stats", {}),
            raw=payload,
        )
        fid = raw.fixture_id
        prev = self.last_stats.get(fid, {})

        if raw.stats:
            self.last_stats[fid] = {**raw.stats}

        event = normalize_event(raw, prev)
        if event is None:
            return

        for cb in self.listeners.get(fid, []):
            try:
                cb(event)
            except Exception as e:
                logger.error("listener_error", fixture_id=fid, error=str(e))

    async def stop(self) -> None:
        self._running = False
        self._abort.set()
