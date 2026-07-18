import asyncio
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

VERBOSITY_MINIMAL = "minimal"
VERBOSITY_STANDARD = "standard"
VERBOSITY_VERBOSE = "verbose"

BROADCASTABLE_ACTIONS: dict[str, tuple[str, str]] = {
    "goal": ("\u26bd GOAL!", "minimal"),
    "halftime_finalised": ("\u23f8\ufe0f Half Time", "minimal"),
    "kickoff": ("\U0001f3af Kickoff", "minimal"),
    "game_finalised": ("\U0001f3c1 Full Time", "minimal"),
    "match_started": ("\U0001f6a9 Match Started", "minimal"),
    "substitution": ("\U0001f504 Substitution", "standard"),
    "var": ("\U0001f4fa VAR", "standard"),
    "var_end": ("\U0001f4fa VAR Decision", "standard"),
    "penalty_awarded": ("\U0001f945 Penalty Awarded", "standard"),
    "penalty_missed": ("\u274c Penalty Missed", "standard"),
    "penalty_save": ("\U0001f9e4 Penalty Saved", "standard"),
    "injury": ("\U0001f915 Injury", "verbose"),
    "shot": ("\U0001f945 Shot", "verbose"),
    "free_kick": ("\U0001f3af Dangerous Free Kick", "verbose"),
}

VERBOSITY_ORDER = {VERBOSITY_MINIMAL: 0, VERBOSITY_STANDARD: 1, VERBOSITY_VERBOSE: 2}


def format_clock(seconds: int | None) -> str:
    if seconds is None:
        return ""
    mins = seconds // 60
    secs = seconds % 60
    if mins >= 45:
        half = "HT" if mins < 60 else ""
    else:
        half = ""
    label = f"{mins}'" if not half else f"{mins}' ({half})"
    return f"\u23f1\ufe0f {label}" if mins > 0 else ""


def format_score(raw: dict) -> tuple[int, int]:
    score = raw.get("Score", raw.get("score", {}))
    p1 = score.get("Participant1", score.get("participant1", {}))
    p2 = score.get("Participant2", score.get("participant2", {}))
    g1 = p1.get("Total", {}).get("Goals", p1.get("total", {}).get("goals", 0))
    g2 = p2.get("Total", {}).get("Goals", p2.get("total", {}).get("goals", 0))
    return int(g1), int(g2)


class MatchBroadcaster:
    def __init__(self, bot, engine, redis_store=None):
        self.bot = bot
        self.engine = engine
        self.redis = redis_store
        self.verbosity: dict[int, str] = {}
        self._last_seq: dict[str, int] = {}

    def set_verbosity(self, chat_id: int, level: str) -> None:
        self.verbosity[chat_id] = level
        if self.redis:
            import asyncio
            asyncio.ensure_future(self.redis.set_verbosity(chat_id, level))

    def get_verbosity(self, chat_id: int) -> str:
        return self.verbosity.get(chat_id, VERBOSITY_STANDARD)

    def _should_broadcast(self, action: str, event, chat_id: int) -> bool:
        if event.type == "card":
            return self.get_verbosity(chat_id) != VERBOSITY_MINIMAL
        if action not in BROADCASTABLE_ACTIONS:
            return False
        _, min_level = BROADCASTABLE_ACTIONS[action]
        group_level = self.get_verbosity(chat_id)
        return VERBOSITY_ORDER.get(group_level, 1) >= VERBOSITY_ORDER.get(min_level, 0)

    def _is_duplicate(self, fixture_id: str, event) -> bool:
        seq = event.raw.seq if event.raw else None
        if seq is None:
            return False
        last = self._last_seq.get(fixture_id, -1)
        if seq <= last:
            return True
        self._last_seq[fixture_id] = seq
        if self.redis:
            import asyncio
            asyncio.ensure_future(self.redis.set_last_seq(fixture_id, seq))
        return False

    async def broadcast(self, event) -> None:
        fid = event.fixture_id
        raw = event.raw
        if raw is None:
            return

        action = raw.action or event.type
        broadcastable = action in BROADCASTABLE_ACTIONS or event.type in ("card",)

        if action == "score_update" or (not broadcastable):
            return

        if self._is_duplicate(fid, event):
            return

        chats = self._tracking_chats(fid)
        if not chats:
            return

        info = self.engine.fixture_info.get(fid, {})
        home = info.get("home", "?")
        away = info.get("away", "?")

        for chat_id in chats:
            if not self._should_broadcast(action, event, chat_id):
                continue
            msg = self._format_message(event, action, home, away, chat_id)
            if msg:
                try:
                    await self.bot.send_message(chat_id, msg)
                except Exception as e:
                    logger.warning("broadcast_failed", chat_id=chat_id, error=str(e))

    def _tracking_chats(self, fid: str) -> list[int]:
        return [c for c, f in self.engine.chat_fixtures.items() if f == fid]

    def _format_message(self, event, action: str, home: str, away: str, chat_id: int) -> str | None:
        raw = event.raw
        payload = raw.raw if raw else {}
        score_g1, score_g2 = format_score(payload)
        clock_str = format_clock(self._get_clock_seconds(payload))
        flag_home = self._flag(home)
        flag_away = self._flag(away)

        if event.type == "card":
            card_type = getattr(event, "card_type", None)
            is_yellow = card_type != "red"
            emoji = "\U0001f7e8" if is_yellow else "\U0001f7e5"
            label = "Yellow Card" if is_yellow else "Red Card"
            player = self._resolve_player_name(event)
            team_side = event.team or ""
            team_name = home if team_side == "team_1" else away
            flag = flag_home if team_side == "team_1" else flag_away
            lines = [f"{emoji} {label}"]
            if team_name:
                lines.append(f"\n{flag} {player or team_name}")
            if clock_str:
                lines.append(clock_str)
            return "\n".join(lines)

        if action == "goal":
            player = self._resolve_player_name(event)
            lines = [
                "\u26bd GOAL!",
                "",
                f"{flag_home} {home} {score_g1}\u2013{score_g2} {away} {flag_away}",
            ]
            if player:
                lines.append(f"\u26bd {player}")
            if clock_str:
                lines.append(clock_str)
            self._append_bet_summary(lines, event)
            return "\n".join(lines)

        if action == "halftime_finalised":
            return f"\u23f8\ufe0f Half Time\n\n{flag_home} {home} {score_g1}\u2013{score_g2} {away} {flag_away}"

        if action == "kickoff":
            clock = payload.get("Clock", payload.get("clock", {}))
            seconds = clock.get("Seconds", clock.get("seconds", 0))
            if seconds and seconds > 60:
                return f"\u25b6\ufe0f Second Half\n\n{flag_home} {home} {score_g1}–{score_g2} {away} {flag_away}"
            return f"\U0001f6a9 Kickoff\n\n{flag_home} {home} vs {away} {flag_away}\n\nLet the banter begin!"

        if action == "game_finalised":
            resolved = sum(1 for b in self.engine.active_bets.values()
                          if b["fixture_id"] == event.fixture_id
                          and b["status"] in ("resolved", "void"))
            lines = [
                "\U0001f3c1 Full Time",
                "",
                f"{flag_home} {home} {score_g1}–{score_g2} {away} {flag_away}",
                "",
                "Thanks for watching with BanterBot!",
            ]
            if resolved:
                lines.append(f"\n\u2705 {resolved} bets settled automatically.\n\U0001f3c6 Leaderboard updated.")
            return "\n".join(lines)

        if action == "substitution":
            player_in = self._resolve_player_id(event.player_in_normative_id)
            player_out = self._resolve_player_id(event.player_out_normative_id)
            team_side = event.team or ""
            team_name = home if team_side == "team_1" else away
            flag = flag_home if team_side == "team_1" else flag_away
            lines = ["\U0001f504 Substitution"]
            if team_name:
                lines.append(f"\n{flag} {team_name}")
            if player_in:
                lines.append(f"\U0001f53c {player_in}")
            if player_out:
                lines.append(f"\U0001f53d {player_out}")
            if clock_str:
                lines.append(clock_str)
            return "\n".join(lines)

        if action in ("var", "var_end"):
            title, _ = BROADCASTABLE_ACTIONS[action]
            outcome = payload.get("Data", payload.get("data", {})).get("Outcome", "")
            lines = [title]
            if outcome:
                lines.append(f"\n{outcome}")
            if clock_str:
                lines.append(clock_str)
            return "\n".join(lines)

        if action == "injury":
            player = self._resolve_player_name(event)
            lines = ["\U0001f915 Injury"]
            if player:
                lines.append(f"\n{player}")
            if clock_str:
                lines.append(clock_str)
            return "\n".join(lines)

        if action in ("match_started",):
            return f"\U0001f6a9 Match Started\n\n{flag_home} {home} vs {away} {flag_away}"

        if action in ("shot",):
            player = self._resolve_player_name(event)
            outcome = payload.get("Data", payload.get("data", {})).get("Outcome", "")
            lines = ["\U0001f945 Shot"]
            if player:
                lines.append(f"\n{player}")
            if outcome:
                lines.append(f"Result: {outcome}")
            if clock_str:
                lines.append(clock_str)
            return "\n".join(lines)

        if action in ("free_kick",):
            fk_type = payload.get("Data", payload.get("data", {})).get("FreeKickType", "")
            lines = ["\U0001f3af Dangerous Free Kick"]
            if fk_type:
                lines.append(f"\n{fk_type}")
            if clock_str:
                lines.append(clock_str)
            return "\n".join(lines)

        if action in ("penalty_awarded", "penalty_missed", "penalty_save"):
            title, _ = BROADCASTABLE_ACTIONS.get(action, (action.upper(), "standard"))
            player = self._resolve_player_name(event)
            lines = [title]
            if player:
                lines.append(f"\n{player}")
            if clock_str:
                lines.append(clock_str)
            return "\n".join(lines)

        return None

    def _get_clock_seconds(self, payload: dict) -> int | None:
        clock = payload.get("Clock", payload.get("clock", {}))
        if isinstance(clock, dict):
            return clock.get("Seconds", clock.get("seconds"))
        return None

    def _resolve_player_name(self, event) -> str | None:
        nid = event.player_normative_id
        if nid is None:
            return None
        fid = event.fixture_id
        player = self.engine.get_player_for_fixture(fid, nid)
        if player:
            return player.get("preferred_name", player.get("match_display"))
        return None

    def _resolve_player_id(self, nid: int | None) -> str | None:
        if nid is None:
            return None
        for fid in self.engine.player_rosters:
            player = self.engine.player_rosters[fid].get(nid)
            if player:
                return player.get("preferred_name")
        return None

    @staticmethod
    def _flag(team: str) -> str:
        from app.core.constants import FLAGS
        return FLAGS.get(team, "\U0001f3df\ufe0f")

    def _append_bet_summary(self, lines: list[str], event) -> None:
        fid = event.fixture_id
        affected = 0
        for bet in self.engine.active_bets.values():
            if bet.get("fixture_id") != fid:
                continue
            if bet.get("status") in ("resolved", "void"):
                continue
            if not bet.get("player_normative_id"):
                continue
            if bet["player_normative_id"] == event.player_normative_id:
                affected += 1
        if affected > 0:
            lines.append(f"\n\U0001f3af {affected} active bet{'s' if affected > 1 else ''} updated.")
