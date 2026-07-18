import uuid
import random
from typing import Any, Callable
from app.core.constants import (
    BET_STATUS_OPEN, BET_STATUS_CALLED, BET_STATUS_FUNDED,
    BET_STATUS_RESOLVED, BET_STATUS_VOID,
    VALID_MARKETS, MARKET_NEXT_GOAL, MARKET_NEXT_CARD, MARKET_NEXT_CORNER,
    MARKET_MATCH_WINNER, UPCOMING_FIXTURES, PLAYER_MARKET_REQUIRED_EVENTS,
)
from app.core.logging import get_logger
from app.services.betting.polls import PollManager, PlayerPoll, poll_manager

logger = get_logger(__name__)

MARKET_LABELS = {
    MARKET_NEXT_GOAL: "next goal",
    MARKET_NEXT_CARD: "next card",
    MARKET_NEXT_CORNER: "next corner",
    MARKET_MATCH_WINNER: "match winner",
}

MARKET_TO_EVENT = {
    MARKET_NEXT_GOAL: ["goal"],
    MARKET_NEXT_CARD: ["card"],
    MARKET_NEXT_CORNER: ["corner"],
    MARKET_MATCH_WINNER: ["score_update"],  # resolved manually at game_finalised
}


class BetStore:
    def __init__(self):
        self._bets: dict[str, dict] = {}

    def create_bet(self, bet_data: dict) -> dict:
        bid = uuid.uuid4().hex[:7]
        bet = {**bet_data, "id": bid, "status": BET_STATUS_OPEN}
        self._bets[bid] = bet
        return bet

    def get_open_bets(self, fixture_id: str) -> list[dict]:
        return [b for b in self._bets.values() if b["fixture_id"] == fixture_id and b["status"] == BET_STATUS_OPEN]

    def update_bet(self, bet_id: str, patch: dict) -> None:
        if bet_id in self._bets:
            self._bets[bet_id].update(patch)

    def get_bet(self, bet_id: str) -> dict | None:
        return self._bets.get(bet_id)

    def get_leaderboard(self, chat_id: int) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for bet in self._bets.values():
            if bet.get("chat_id") == chat_id and bet["status"] == BET_STATUS_RESOLVED:
                winner = bet.get("winner", "")
                loser = bet.get("opponent") if bet.get("winner") == bet.get("creator") else bet.get("creator")
                if winner:
                    stats.setdefault(winner, {"wins": 0, "losses": 0})["wins"] += 1
                if loser:
                    stats.setdefault(loser, {"wins": 0, "losses": 0})["losses"] += 1
        return stats


class BetEngine:
    def __init__(self, store: BetStore, stream, bot, payments, nlu):
        self.store = store
        self.stream = stream
        self.bot = bot
        self.payments = payments
        self.nlu = nlu
        self.active_bets: dict[str, dict] = {}
        self.chat_fixtures: dict[int, str] = {}
        self.fixture_info: dict[str, dict] = {}
        self.tracked: set[str] = set()

    def fixture_label(self, fid: str) -> str:
        info = self.fixture_info.get(fid, {})
        return f"{info.get('home', '?')} vs {info.get('away', '?')}"

    def _ensure_tracked(self, fid: str) -> None:
        if fid in self.tracked:
            return
        self.tracked.add(fid)
        self.stream.on_match_event(fid, self._on_event)

    def _on_event(self, event) -> None:
        import asyncio
        asyncio.ensure_future(self._resolve_event(event))

    def _determine_match_winner(self, bet: dict, final_stats: dict) -> str | None:
        info = self.fixture_info.get(bet["fixture_id"], {})
        home = info.get("home", "").lower()
        away = info.get("away", "").lower()
        bet_team = (bet.get("team") or "").lower()
        p1 = int(final_stats.get("1", 0))
        p2 = int(final_stats.get("2", 0))
        if p1 == p2:
            return None
        winning_name = home if p1 > p2 else away
        winning_side = "home" if p1 > p2 else "away"
        if bet_team in (home, away):
            return "creator_team" if bet_team == winning_name else "opponent_team"
        if bet_team in ("home", "away"):
            return "creator_team" if bet_team == winning_side else "opponent_team"
        return None

    async def _send_poll_keyboard(self, chat_id: int, poll: PlayerPoll) -> None:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"\u2705 Yes ({len(poll.votes_yes)})",
                                  callback_data=f"poll:vote:{poll.poll_id}:yes"),
             InlineKeyboardButton(text=f"\u274c No ({len(poll.votes_no)})",
                                  callback_data=f"poll:vote:{poll.poll_id}:no")],
        ])
        try:
            await self.bot.send_message(chat_id, "Vote:", reply_markup=kb)
        except Exception:
            pass

    async def _resolve_event(self, event) -> None:
        raw = event.raw.raw if event.raw else {}
        if raw.get("action") == "game_finalised":
            final_stats = raw.get("stats", {})

            for bid, bet in list(self.active_bets.items()):
                if bet["fixture_id"] != event.fixture_id:
                    continue
                if bet["status"] in (BET_STATUS_RESOLVED, BET_STATUS_VOID):
                    continue

                if bet["market"] == MARKET_MATCH_WINNER:
                    winner_team = self._determine_match_winner(bet, final_stats)
                    if winner_team:
                        winner_user = bet["creator"] if winner_team == "creator_team" else bet.get("opponent")
                        self.store.update_bet(bid, {"status": BET_STATUS_RESOLVED, "winner": winner_user})
                        loser = bet.get("opponent") if winner_user == bet["creator"] else bet["creator"]
                        msg = (
                            f"\U0001f3c6 {winner_user} wins! "
                            f"Match result settled.\n"
                            f"{loser}, you owe a round."
                        )
                        try:
                            await self.bot.send_message(bet["chat_id"], msg)
                        except Exception:
                            pass
                elif bet.get("player"):
                    confirmed = bet.get("confirmed_events", 0)
                    required = PLAYER_MARKET_REQUIRED_EVENTS.get(bet.get("player_market", "scores"), 1)
                    if required > 0 and confirmed >= required:
                        winner_user = bet["creator"]
                        self.store.update_bet(bid, {"status": BET_STATUS_RESOLVED, "winner": winner_user})
                        try: await self.bot.send_message(bet["chat_id"],
                            f"\U0001f3c6 {bet['player']} bet won! {confirmed}/{required} events confirmed.")
                        except Exception: pass
                    else:
                        self.store.update_bet(bid, {"status": BET_STATUS_VOID})
                        try: await self.bot.send_message(bet["chat_id"],
                            f"\u26d4 {bet['player']} bet lost — only {confirmed}/{required} events confirmed.")
                        except Exception: pass
                    self.active_bets.pop(bid, None)
                else:
                    self.store.update_bet(bid, {"status": BET_STATUS_VOID})
                    self.active_bets.pop(bid, None)
                    try:
                        await self.bot.send_message(bet["chat_id"],
                            f"\u26d4 Match ended — bet `{bid[:4]}` voided without resolution.")
                    except Exception: pass
            return

        open_bets = self.store.get_open_bets(event.fixture_id)
        all_live = open_bets + [b for b in self.active_bets.values()
                                if b["fixture_id"] == event.fixture_id
                                and b["status"] not in (BET_STATUS_RESOLVED, BET_STATUS_VOID)]
        seen: set[str] = set()

        for bet in all_live:
            if bet["id"] in seen or bet["status"] in (BET_STATUS_RESOLVED, BET_STATUS_VOID):
                continue
            seen.add(bet["id"])

            # Player-specific bets → trigger confirmation poll
            player = bet.get("player")
            player_market = bet.get("player_market")
            if player and player_market and event.type in ("goal", "card"):
                if bet.get("team") and event.team and bet["team"] != event.team:
                    continue  # event is for wrong team
                existing_polls = [p for p in poll_manager._polls.values()
                                  if p.bet_id == bet["id"] and not p.resolved]
                if existing_polls:
                    continue  # already an active poll for this bet
                poll = poll_manager.create(
                    bet_id=bet["id"], chat_id=bet["chat_id"],
                    player=player, event_type=event.type,
                    event_description=f"{event.type.upper()} detected",
                    participants=[bet["creator"], bet.get("opponent", "")],
                )
                try:
                    await self.bot.send_message(bet["chat_id"],
                        f"\u26bd {event.type.upper()}!\n\n"
                        f"Was this {player}?\n\n"
                        f"\u2705 Yes ({len(poll.votes_yes)})  \u274c No ({len(poll.votes_no)})\n"
                        f"Tap below to vote:",
                    )
                    # Trigger poll keyboard via bot
                    await self._send_poll_keyboard(bet["chat_id"], poll)
                except Exception:
                    pass
                continue

            allowed_events = MARKET_TO_EVENT.get(bet["market"], [])
            if event.type not in allowed_events:
                continue

            winner = bet["creator"]
            self.store.update_bet(bet["id"], {"status": BET_STATUS_RESOLVED, "winner": winner})
            self.active_bets.pop(bet["id"], None)

            loser = bet.get("opponent", "the room")
            taunts = [
                f"\U0001f3c6 {winner} takes it! {loser} just got bantered.",
                f"\U0001f389 {winner} wins the {MARKET_LABELS.get(bet['market'], '')} bet. {loser}, you owe a round.",
                f"\U0001f525 {winner} called it. {loser}, see you on the leaderboard.",
            ]
            msg = random.choice(taunts)

            try:
                from app.services.txline.provenance import get_proof_for_event
                proof = await get_proof_for_event(event.fixture_id, event.raw.seq or 0, 1, event.timestamp)
                if proof:
                    msg += f"\n\n\U0001f50d Verifiable proof: {proof}"
            except Exception:
                msg += "\n\n\u26a0\ufe0f Proof unavailable"

            try:
                await self.bot.send_message(bet["chat_id"], msg)
            except Exception as e:
                logger.error("resolve_post_failed", error=str(e))

    async def validate_fixture(self, fid: str) -> dict | None:
        import httpx
        from app.core.config import settings
        from app.core.dependencies import get_container
        container = get_container()
        jwt = container.credentials.jwt if container.credentials else ""
        api_token = container.credentials.api_token if container.credentials else ""
        api_base = f"{settings.txline_api_origin}/api"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{api_base}/scores/snapshot/{fid}?asOf=0",
                    headers={"Authorization": f"Bearer {jwt}", "X-Api-Token": api_token},
                )
                if resp.status_code == 200:
                    for f in UPCOMING_FIXTURES:
                        if f["id"] == fid:
                            return f
                    return {"id": fid, "home": "?", "away": "?", "stage": "?", "time_utc": "?"}
        except Exception:
            pass
        return None
