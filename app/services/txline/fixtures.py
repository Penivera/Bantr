import httpx
from datetime import datetime, timezone
from typing import Any
from app.core.config import settings
from app.core.logging import get_logger
from app.services.txline.auth import TxLineCredentials

logger = get_logger(__name__)

# GameState flags documented in the TxLINE "Fetching Snapshots" reference.
GAME_STATE_SCHEDULED = 1
GAME_STATE_FINISHED = 3
GAME_STATE_CANCELLED = 6

FINISHED_STATES = {GAME_STATE_FINISHED, GAME_STATE_CANCELLED}


def _normalize_fixture(raw: dict[str, Any]) -> dict | None:
    try:
        fixture_id = str(raw["FixtureId"])
    except (KeyError, TypeError):
        return None

    # Skip cancelled/voided fixtures; only scheduled (and any live state) matter.
    game_state = raw.get("GameState") or raw.get("gameState")
    if game_state in FINISHED_STATES:
        return None

    p1 = raw.get("Participant1") or "?"
    p2 = raw.get("Participant2") or "?"
    p1_is_home = raw.get("Participant1IsHome", True)
    home, away = (p1, p2) if p1_is_home else (p2, p1)

    start_raw = raw.get("StartTime")
    if isinstance(start_raw, (int, float)):
        time_utc = datetime.fromtimestamp(start_raw, tz=timezone.utc).isoformat()
    elif isinstance(start_raw, str):
        time_utc = start_raw
    else:
        time_utc = ""

    # FixtureGroup / CompetitionName vary per payload; prefer the most specific.
    stage = (
        raw.get("FixtureGroup")
        or raw.get("CompetitionName")
        or raw.get("Competition")
        or ""
    )

    return {
        "id": fixture_id,
        "home": home,
        "away": away,
        "time_utc": time_utc,
        "stage": stage,
    }


async def fetch_fixtures(credentials: TxLineCredentials) -> list[dict]:
    """Pull the current fixture list from TxLINE's /api/fixtures/snapshot.

    Returns a list of normalized fixtures sorted by start time ascending:
    [{id, home, away, time_utc, stage}, ...]
    """
    api_base = f"{settings.txline_api_origin}/api"
    headers = {
        "Authorization": f"Bearer {credentials.jwt}",
        "X-Api-Token": credentials.api_token,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{api_base}/fixtures/snapshot", headers=headers)
        resp.raise_for_status()
        payload = resp.json()

    if not isinstance(payload, list):
        logger.warning("fixtures_snapshot_unexpected_shape", type=type(payload).__name__)
        return []

    normalized = [f for f in (_normalize_fixture(item) for item in payload) if f]
    normalized.sort(key=lambda f: f["time_utc"] or "")
    logger.info("fixtures_fetched", count=len(normalized))
    return normalized
