import uuid
import random
import asyncio
from typing import Any, Callable
from app.core.constants import (
    BET_STATUS_OPEN, BET_STATUS_CALLED, BET_STATUS_FUNDED,
    BET_STATUS_RESOLVED, BET_STATUS_VOID,
    VALID_MARKETS, MARKET_NEXT_GOAL, MARKET_NEXT_CARD, MARKET_NEXT_CORNER,
    MARKET_MATCH_WINNER, UPCOMING_FIXTURES, PLAYER_MARKET_REQUIRED_EVENTS,
)
from app.core.logging import get_logger
from app.services.betting.polls import PollManager, PlayerPoll, poll_manager
from app.services.betting.players import PLAYER_ACTION_TYPES, PARTICIPANT_TO_TEAM, resolve_player_from_roster

logger = get_logger(__name__)

MARKET_LABELS = {
    MARKET_NEXT_GOAL: "next goal",
    MARKET_NEXT_CARD: "next card",
    MARKET_NEXT_CORNER: "next corner",
    MARKET_MATCH_WINNER: "match winner",
    "hat_trick": "hat trick",
    "first_scorer": "first scorer",
    "two_goals": "two goals",
    "scores": "scores",
    "player_card": "player card",
    "clean_sheet": "clean sheet",
}

MARKET_TO_EVENT = {
    MARKET_NEXT_GOAL: ["goal"],
    MARKET_NEXT_CARD: ["card"],
    MARKET_NEXT_CORNER: ["corner"],
}


class BetStore:
    def __init__(self, redis_store=None):
        self._bets: dict[str, dict] = {}
        self.redis = redis_store

    def create_bet(self, bet_data: dict) -> dict:
        import time
        bid = uuid.uuid4().hex[:7]
        bet = {
            **bet_data,
            "id": bid,
            "status": BET_STATUS_OPEN,
            "created_at": int(time.time()),
        }
        self._bets[bid] = bet
        if self.redis:
            import asyncio
            asyncio.ensure_future(self.redis.save_bet(bet))
        self._persist_to_db(bet)
        return bet

    def get_open_bets(self, fixture_id: str) -> list[dict]:
        return [b for b in self._bets.values() if b.get("fixture_id") == fixture_id and b.get("status") == BET_STATUS_OPEN]

    def update_bet(self, bet_id: str, patch: dict) -> None:
        if bet_id in self._bets:
            self._bets[bet_id].update(patch)
        if self.redis:
            import asyncio
            status = patch.get("status")
            if status:
                import time
                extra = {k: v for k, v in patch.items() if k != "status"}
                if status == BET_STATUS_CALLED:
                    extra["accepted_at"] = int(time.time())
                elif status in (BET_STATUS_RESOLVED, BET_STATUS_VOID):
                    extra["settled_at"] = int(time.time())
                asyncio.ensure_future(self.redis.update_bet_status(bet_id, status, extra))
            else:
                bet = self.get_bet(bet_id)
                if bet:
                    asyncio.ensure_future(self.redis.save_bet(bet))
        self._persist_to_db(self.get_bet(bet_id))

    def _persist_to_db(self, bet: dict | None) -> None:
        if not bet:
            return
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._async_persist_to_db(bet))
        except RuntimeError:
            pass

    async def _async_persist_to_db(self, bet: dict) -> None:
        try:
            from app.db.session import async_session
            from app.db.models import Bet as BetModel
            from sqlalchemy import select
            async with async_session() as s:
                existing = (await s.execute(select(BetModel).where(BetModel.bet_id == bet["id"]))).scalar_one_or_none()
                if existing:
                    existing.status = bet.get("status", existing.status)
                    existing.stake_amount = bet.get("amount", existing.stake_amount)
                    existing.opponent_username = bet.get("opponent", existing.opponent_username)
                    existing.creator_wallet = bet.get("creator_wallet", existing.creator_wallet)
                    existing.opponent_wallet = bet.get("opponent_wallet", existing.opponent_wallet)
                    existing.payment_reference = bet.get("payment_reference", existing.payment_reference)
                    existing.tx_signature = bet.get("tx_signature", existing.tx_signature)
                    existing.winner = bet.get("winner", existing.winner)
                    import time, datetime
                    status = bet.get("status")
                    if status == "called":
                        existing.accepted_at = datetime.datetime.fromtimestamp(bet.get("accepted_at", time.time()), tz=datetime.timezone.utc).replace(tzinfo=None)
                    elif status in ("resolved", "void"):
                        ts = bet.get("settled_at", time.time())
                        if isinstance(ts, (int, float)):
                            existing.settled_at = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).replace(tzinfo=None)
                        else:
                            existing.settled_at = ts
                    elif status == "void" and bet.get("creator") == existing.creator_username:
                        import datetime
                        existing.cancelled_at = datetime.datetime.now(datetime.timezone.utc)
                else:
                    s.add(BetModel(
                        bet_id=bet["id"],
                        creator_username=bet.get("creator", ""),
                        opponent_username=bet.get("opponent"),
                        chat_id=bet.get("chat_id"),
                        fixture_id=bet.get("fixture_id", ""),
                        market=bet.get("market", ""),
                        stake_amount=bet.get("amount", 0),
                        stake_token="USDC",
                        status=bet.get("status", "open"),
                        payment_reference=bet.get("payment_reference"),
                    ))
                await s.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"db_persist_bet_failed bet_id={bet.get('id')}: {e}")

    async def load_from_db(self) -> None:
        pass  # DB queried on-demand via get_bet / get_bets_for_user

    def get_bet(self, bet_id: str) -> dict | None:
        bet = self._bets.get(bet_id)
        if bet:
            return bet
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._load_bet_from_db(bet_id))
        except RuntimeError:
            return None
        return None

    async def get_bet_async(self, bet_id: str) -> dict | None:
        bet = self._bets.get(bet_id)
        if bet:
            return bet
        return await self._load_bet_from_db(bet_id)

    async def _load_bet_from_db(self, bet_id: str) -> dict | None:
        try:
            from app.db.session import async_session
            from app.db.models import Bet as BetModel
            from sqlalchemy import select
            async with async_session() as s:
                row = (await s.execute(select(BetModel).where(BetModel.bet_id == bet_id))).scalar_one_or_none()
                if not row:
                    return None
                bet = self._row_to_bet(row)
                return bet
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"db_load_bet_failed bet_id={bet_id}: {e}")
            return None

    async def find_bet_by_prefix(self, prefix: str) -> dict | None:
        for bid, bet in self._bets.items():
            if bid.startswith(prefix):
                return bet
        try:
            from app.db.session import async_session
            from app.db.models import Bet as BetModel
            from sqlalchemy import select
            async with async_session() as s:
                rows = (await s.execute(select(BetModel).where(BetModel.bet_id.startswith(prefix)))).scalars().all()
                if rows:
                    return self._row_to_bet(rows[0])
        except Exception:
            pass
        return None

    def _row_to_bet(self, row) -> dict:
        bet = {
            "id": row.bet_id,
            "creator": row.creator_username,
            "opponent": row.opponent_username,
            "chat_id": row.chat_id,
            "fixture_id": row.fixture_id,
            "market": row.market,
            "amount": row.stake_amount,
            "status": row.status,
            "winner": row.winner,
            "payment_reference": row.payment_reference,
            "tx_signature": row.tx_signature,
            "creator_wallet": row.creator_wallet,
            "opponent_wallet": row.opponent_wallet,
            "created_at": int(row.created_at.timestamp()) if row.created_at else 0,
        }
        self._bets[row.bet_id] = bet
        return bet

    def get_leaderboard(self, chat_id: int) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for bet in self._bets.values():
            if bet.get("chat_id") == chat_id and bet.get("status") == BET_STATUS_RESOLVED:
                winner = bet.get("winner", "")
                loser = bet.get("opponent") if bet.get("winner") == bet.get("creator") else bet.get("creator")
                if winner:
                    stats.setdefault(winner, {"wins": 0, "losses": 0})["wins"] += 1
                if loser:
                    stats.setdefault(loser, {"wins": 0, "losses": 0})["losses"] += 1
        return stats


class BetEngine:
    def __init__(self, store: BetStore, stream, bot, payments, nlu, redis_store=None):
        self.store = store
        self.stream = stream
        self.bot = bot
        self.payments = payments
        self.nlu = nlu
        self.redis = redis_store
        self.active_bets: dict[str, dict] = {}
        self.chat_fixtures: dict[int, str] = {}
        self.fixture_info: dict[str, dict] = {}
        self.tracked: set[str] = set()
        self.player_rosters: dict[str, dict[int, dict]] = {}
        self.all_players_by_fixture: dict[str, list[dict]] = {}
        self._rosters_fetching: set[str] = set()
        from app.services.betting.broadcaster import MatchBroadcaster
        self.broadcaster = MatchBroadcaster(bot, self, redis_store=redis_store)

    async def restore_from_redis(self) -> None:
        if not self.redis:
            return
        try:
            chat_fixtures = await self.redis.get_all_chat_fixtures()
            self.chat_fixtures = chat_fixtures
            tracked = await self.redis.get_all_tracked()
            self.tracked = tracked
            for fid in tracked:
                self.stream.on_match_event(fid, self._on_event)
            verbosities = await self.redis.get_all_verbosities()
            for chat_id, level in verbosities.items():
                self.broadcaster.set_verbosity(chat_id, level)
            logger.info("redis_restored", chats=len(chat_fixtures), tracked=len(tracked))
        except Exception as e:
            logger.warning("redis_restore_failed", error=str(e))

    def fixture_label(self, fid: str) -> str:
        info = self.fixture_info.get(fid, {})
        return f"{info.get('home', '?')} vs {info.get('away', '?')}"

    def track_fixture_for_chat(self, chat_id: int, fid: str) -> None:
        self.chat_fixtures[chat_id] = fid
        self._ensure_tracked(fid)
        if self.redis:
            asyncio.ensure_future(self.redis.set_chat_fixture(chat_id, fid))

    def _ensure_tracked(self, fid: str) -> None:
        if fid in self.tracked:
            return
        self.tracked.add(fid)
        self.stream.on_match_event(fid, self._on_event)
        asyncio.ensure_future(self._fetch_rosters(fid))
        if self.redis:
            asyncio.ensure_future(self.redis.add_tracked(fid))

    async def _fetch_rosters(self, fid: str) -> None:
        if fid in self._rosters_fetching:
            return
        self._rosters_fetching.add(fid)
        try:
            from app.services.betting.roster import fetch_fixture_roster, build_player_lookup
            from app.core.dependencies import get_container
            container = get_container()
            rosters = await fetch_fixture_roster(fid, container.credentials)
            if rosters:
                lookup = build_player_lookup(rosters)
                self.player_rosters[fid] = lookup
                all_players = []
                for team_name, players in rosters.items():
                    for p in players:
                        p["team_name"] = team_name
                        all_players.append(p)
                self.all_players_by_fixture[fid] = all_players
                logger.info("rosters_cached", fixture_id=fid, player_count=len(lookup))
        except Exception as e:
            logger.error("roster_fetch_error", fixture_id=fid, error=str(e))
        finally:
            self._rosters_fetching.discard(fid)

    def get_player_for_fixture(self, fid: str, normative_id: int | None) -> dict | None:
        if fid in self.player_rosters and normative_id is not None:
            return self.player_rosters[fid].get(normative_id)
        return None

    def resolve_player_name(self, fid: str, name: str) -> list[dict]:
        if fid in self.all_players_by_fixture:
            return resolve_player_from_roster(name, self.all_players_by_fixture[fid])
        return []

    def _on_event(self, event) -> None:
        asyncio.ensure_future(self._on_event_async(event))

    async def _on_event_async(self, event) -> None:
        await self.broadcaster.broadcast(event)
        await self._resolve_event(event)

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
                if bet["status"] in (BET_STATUS_RESOLVED, BET_STATUS_VOID, BET_STATUS_OPEN):
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
                    self.active_bets.pop(bid, None)
                    continue

                is_player_bet = bool(bet.get("player") or bet.get("player_normative_id"))
                if is_player_bet:
                    player_display = bet.get("player_display", bet.get("player", "?"))
                    confirmed = bet.get("confirmed_events", 0)
                    required = PLAYER_MARKET_REQUIRED_EVENTS.get(bet.get("player_market", "scores"), 1)
                    if bet.get("player_market") == "clean_sheet":
                        self.store.update_bet(bid, {"status": BET_STATUS_RESOLVED, "winner": bet["creator"]})
                        try:
                            await self.bot.send_message(bet["chat_id"],
                                f"\U0001f3c6 {player_display} clean sheet — {bet['creator']} wins!")
                        except Exception:
                            pass
                    elif required > 0 and confirmed >= required:
                        self.store.update_bet(bid, {"status": BET_STATUS_RESOLVED, "winner": bet["creator"]})
                        try:
                            await self.bot.send_message(bet["chat_id"],
                                f"\U0001f3c6 {player_display}: {confirmed}/{required} — {bet['creator']} wins!")
                        except Exception:
                            pass
                    else:
                        self.store.update_bet(bid, {"status": BET_STATUS_VOID})
                        try:
                            await self.bot.send_message(bet["chat_id"],
                                f"\u26d4 {player_display}: only {confirmed}/{required} — bet voided.")
                        except Exception:
                            pass
                    self.active_bets.pop(bid, None)
                    continue

                self.store.update_bet(bid, {"status": BET_STATUS_VOID})
                self.active_bets.pop(bid, None)
                try:
                    await self.bot.send_message(bet["chat_id"],
                        f"\u26d4 Match ended — bet `{bid[:4]}` voided without resolution.")
                except Exception:
                    pass
            return

        all_live = [b for b in self.active_bets.values()
                    if b["fixture_id"] == event.fixture_id
                    and b["status"] not in (BET_STATUS_RESOLVED, BET_STATUS_VOID, BET_STATUS_OPEN)]
        seen: set[str] = set()

        for bet in all_live:
            if bet["id"] in seen or bet["status"] in (BET_STATUS_RESOLVED, BET_STATUS_VOID, BET_STATUS_OPEN):
                continue
            seen.add(bet["id"])

            is_player_bet = bool(bet.get("player") or bet.get("player_normative_id"))
            player_normative_id = bet.get("player_normative_id")

            if is_player_bet and event.type in ("goal", "card", "substitution", "injury"):
                event_nid = event.player_normative_id
                event_team = event.team

                if bet.get("team") and event_team and bet["team"] != event_team:
                    continue

                if event_nid and player_normative_id and event_nid == player_normative_id:
                    self._handle_player_event_confirmed(bet, event)
                    continue

                if event_nid and player_normative_id is None:
                    self._handle_player_event_confirmed(bet, event)
                    continue

                if event_nid is None:
                    existing_polls = poll_manager.active_for_bet(bet["id"])
                    if existing_polls:
                        continue
                    player_disp = bet.get("player_display", bet.get("player", "?"))
                    poll = poll_manager.create(
                        bet_id=bet["id"], chat_id=bet["chat_id"],
                        player=player_disp, event_type=event.type,
                        event_description=f"{event.type.upper()} detected (P{event.raw.participant})",
                        participants=[bet["creator"], bet.get("opponent", "")],
                    )
                    try:
                        await self.bot.send_message(bet["chat_id"],
                            f"\u26bd {event.type.upper()}!\n\n"
                            f"Was this {player_disp}?\n\n"
                            f"\u2705 Yes ({len(poll.votes_yes)})  \u274c No ({len(poll.votes_no)})\n"
                            f"Tap below to vote:",
                        )
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

    def _handle_player_event_confirmed(self, bet: dict, event) -> None:
        bet_id = bet["id"]
        player_disp = bet.get("player_display", bet.get("player", "?"))
        confirmed = bet.get("confirmed_events", 0) + 1
        player_market = bet.get("player_market", "scores")
        required = PLAYER_MARKET_REQUIRED_EVENTS.get(player_market, 1)

        if bet_id in self.active_bets:
            self.active_bets[bet_id]["confirmed_events"] = confirmed

        emoji_map = {"goal": "\u26bd", "card": "\U0001fe0f", "substitution": "\U0001f504", "injury": "\U0001f915"}
        emoji = emoji_map.get(event.type, "\u26bd")

        try:
            msg = f"{emoji} {event.type.upper()}\n\n{player_disp}\n\nProgress: {confirmed} / {required} goals"
            if bet.get("player_market") == "player_card":
                msg = f"{emoji} {event.type.upper()}\n\n{player_disp}\n\nCard confirmed: {confirmed} / {required}"
            elif bet.get("player_market") == "clean_sheet":
                msg = f"{emoji} Clean sheet intact for {player_disp}"
            asyncio.ensure_future(self.bot.send_message(bet["chat_id"], msg))
        except Exception:
            pass

        if required > 0 and confirmed >= required:
            self.store.update_bet(bet_id, {"status": BET_STATUS_RESOLVED, "winner": bet["creator"], "confirmed_events": confirmed})
            self.active_bets.pop(bet_id, None)
            try:
                msg = f"\U0001f3c6 {player_disp}: {confirmed}/{required} confirmed — {bet['creator']} wins!"
                asyncio.ensure_future(self.bot.send_message(bet["chat_id"], msg))
            except Exception:
                pass

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
                    info = self.fixture_info.get(fid)
                    if info:
                        return info
                    return {"id": fid, "home": "?", "away": "?", "stage": "?", "time_utc": "?"}
        except Exception:
            pass
        return None
