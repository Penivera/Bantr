from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup,
    KeyboardButton, CallbackQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
import re
import asyncio as _asyncio
from app.core.config import settings
from app.core.constants import (
    VALID_MARKETS, UPCOMING_FIXTURES, MARKET_MATCH_WINNER,
    BET_STATUS_RESOLVED, BET_STATUS_VOID, flag_for, PLAYER_MARKET_REQUIRED_EVENTS,
    PLAYER_MARKETS, PLAYER_MARKET_VALUES,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Keyboards ──

REPLY_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="\u26bd Fixtures"), KeyboardButton(text="\U0001f3af Track")],
        [KeyboardButton(text="\U0001f4b0 Bet"), KeyboardButton(text="\U0001f3c6 Leaderboard")],
        [KeyboardButton(text="\u2753 Help")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Tap a button or type naturally...",
)

KEYBOARD_MAP: dict[str, str] = {
    "\u26bd Fixtures": "fixtures", "\U0001f3af Track": "track",
    "\U0001f4b0 Bet": "bet", "\U0001f3c6 Leaderboard": "leaderboard",
    "\u2753 Help": "help",
}


def _inline_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\u26bd Fixtures", callback_data="menu:fixtures"),
            InlineKeyboardButton(text="\U0001f3c6 Leaderboard", callback_data="menu:leaderboard"),
        ],
        [
            InlineKeyboardButton(text="\U0001f3af Track Match", callback_data="menu:fixtures"),
            InlineKeyboardButton(text="\U0001f4d6 Help", callback_data="menu:help"),
        ],
        [
            InlineKeyboardButton(text="\U0001f916 Add to Group",
                url=f"https://t.me/{settings.telegram_bot_username}?startgroup=start"),
        ],
    ])


def _fixture_label(f: dict) -> str:
    return f"{flag_for(f['home'])} {f['home']} vs {flag_for(f['away'])} {f['away']}"


def _fixture_keyboard(available) -> InlineKeyboardMarkup:
    available = list(available)
    builder = InlineKeyboardBuilder()
    for f in available:
        builder.button(text=_fixture_label(f), callback_data=f"menu:track:{f['id']}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="\U0001f519 Back", callback_data="menu:start"))
    return builder.as_markup()


# ── Alias map (no AI) ──

ALIASES: dict[str, str] = {
    "fixtures": "fixtures", "matches": "fixtures", "games": "fixtures",
    "show fixtures": "fixtures", "show matches": "fixtures",
    "today fixtures": "fixtures", "today's matches": "fixtures",
    "upcoming": "fixtures", "what matches": "fixtures", "who playing": "fixtures",
    "leaderboard": "leaderboard", "rankings": "leaderboard",
    "show leaderboard": "leaderboard", "scoreboard": "leaderboard",
    "help": "help", "commands": "help", "what can you do": "help",
    "how does this work": "help", "how to bet": "help",
    "track": "track", "track match": "track", "select match": "track", "pick match": "track",
}

BET_MARKET_MAP: dict[str, str] = {
    "next goal": "next_goal", "goal": "next_goal", "scores": "scores", "score": "scores",
    "next card": "next_card", "card": "player_card", "booking": "player_card",
    "yellow": "next_card", "red": "next_card",
    "next corner": "next_corner", "corner": "next_corner",
    "wins": "match_winner", "win": "match_winner", "winner": "match_winner",
    "will win": "match_winner", "to win": "match_winner", "beat": "match_winner",
    "hat trick": "hat_trick", "hattrick": "hat_trick", "hat-trick": "hat_trick",
    "first scorer": "first_scorer", "first goal": "first_scorer", "scores first": "first_scorer",
    "two goals": "two_goals", "brace": "two_goals", "2 goals": "two_goals",
    "booked": "player_card", "red card": "player_card",
    "clean sheet": "clean_sheet", "cleansheet": "clean_sheet",
}

# e.g. "@alice 50 next goal" or "@alice next goal 50" or "bet @alice 50 on Mbappe to score"
BET_REGEX = re.compile(
    r'@(\w+)\s+\$?(\d+(?:\.\d+)?)\s*(.+?)(?:\s+(.+))?$',
    re.IGNORECASE,
)

# ── Deterministic bet parser ──

def _parse_bet(text: str) -> dict | None:
    """Try to parse a bet message without AI. Returns {opponent, amount, market, team, player} or None."""
    m = BET_REGEX.search(text)
    if not m:
        return None
    opponent = f"@{m.group(1)}"
    amount = m.group(2)
    rest = (m.group(3) or "").strip().lower()
    if m.group(4):
        rest = rest + " " + m.group(4).strip().lower()

    # Try to match a known market in the remaining text
    market = None
    team = None
    for key, val in sorted(BET_MARKET_MAP.items(), key=lambda x: -len(x[0])):
        if f" {key} " in f" {rest} ":
            market = val
            rest = rest.replace(key, "", 1).strip()
            break

    if not market and rest:
        first_word = rest.split()[0] if rest.split() else None
        if first_word and first_word in BET_MARKET_MAP:
            market = BET_MARKET_MAP[first_word]
            rest = rest[len(first_word):].strip()
        elif first_word and first_word in VALID_MARKETS:
            market = first_word
            rest = rest[len(first_word):].strip()

    if market and market not in VALID_MARKETS:
        market = None

    extra = m.group(4)
    if market and market in PLAYER_MARKET_VALUES and rest:
        return {"opponent": opponent, "amount": amount, "market": market, "player": rest}

    if extra:
        team = extra.strip()
    elif rest:
        team = rest.strip() if rest else None

    if team and team.lower() in BET_MARKET_MAP:
        team = None

    if not market and not team:
        return None

    return {"opponent": opponent, "amount": amount, "market": market, "team": team}


# ── Help text ──

def _fmt_market(m: str) -> str:
    return m.replace("_", " ").title()

HELP_TEXT = """\U0001f4d6 *Available Commands*

\U0001f4c5 /fixtures — View upcoming matches
\U0001f3af /track — Select which fixture to bet on
\U0001f4b0 /bet @user <market> <amount> — Challenge someone
\u2705 /call <bet_id> — Accept a pending bet
\U0001f3c6 /leaderboard — View rankings

*Standard markets:* """ + ", ".join(_fmt_market(m) for m in ["next_goal", "next_card", "next_corner", "match_winner"]) + """

*Player markets:* """ + ", ".join(_fmt_market(m) for m in PLAYER_MARKET_VALUES) + """

\U0001f9e0 *Natural Language*
\U0001f4b0 /bet @alice next_goal 50
\U0001f4b0 /bet @alice hat_trick 50 Mbappe
\U0001f4b0 Mbappe scores first — I bet @bob 50

*Match winner* resolves at full time — winner takes the pot.
*Player bets* resolve automatically when the player performs the action."""


class TelegramBot:
    def __init__(self, container):
        self.container = container
        self.bot: Bot | None = None
        self.dp: Dispatcher | None = None
        self._router = Router()

    async def send_message(self, chat_id: int, text: str) -> None:
        if self.bot:
            await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=REPLY_KEYBOARD)

    @staticmethod
    def _username(event) -> str:
        user = event.from_user
        if user and user.username:
            return f"@{user.username}"
        return str(user.id) if user else "unknown"

    async def _reply(self, event, text: str, **kwargs) -> types.Message:
        return await event.answer(text, reply_markup=REPLY_KEYBOARD, **kwargs)

    def _tracked_label(self, chat_id: int) -> str | None:
        engine = self.container.engine
        fid = engine.chat_fixtures.get(chat_id)
        if fid and fid in engine.fixture_info:
            info = engine.fixture_info[fid]
            return _fixture_label({"home": info["home"], "away": info["away"]})
        return None

    # ── /start ──

    async def cmd_start(self, message: types.Message) -> None:
        await message.answer(
            "\U0001f3c6 *Welcome to BanterBot!*\n\n"
            "Turn your group chat into a live World Cup betting arena.\n\n"
            "\u26bd Track matches in real time\n"
            "\U0001f91d Challenge friends with bets\n"
            "\U0001f50d Verify results with on-chain proofs\n"
            "\U0001f9e0 Or just chat naturally — I understand plain English.",
            parse_mode="Markdown", reply_markup=_inline_menu())

    # ── /help ──

    async def cmd_help(self, message: types.Message) -> None:
        await message.answer(HELP_TEXT)

    async def _help_callback(self, callback: CallbackQuery) -> None:
        await callback.message.edit_text(HELP_TEXT, reply_markup=_inline_menu())

    # ── /fixtures ──

    async def cmd_fixtures(self, message: types.Message) -> None:
        engine = self.container.engine
        available = engine.fixture_info.values()
        if not available:
            await self._reply(message, "No upcoming fixtures available.")
            return
        tracked = engine.chat_fixtures.get(message.chat.id)
        lines = ["\U0001f4c5 *Available fixtures*\n_Tap a match to track it:_"]
        for f in available:
            tag = "  \u2705 tracked" if f["id"] == tracked else ""
            lines.append(_fixture_label(f) + tag)
        await message.answer("\n".join(lines), parse_mode="Markdown",
                            reply_markup=_fixture_keyboard(available))

    # ── /track ──

    async def cmd_track(self, message: types.Message, command=None) -> None:
        engine = self.container.engine
        available = engine.fixture_info.values()
        if not available:
            await self._reply(message, "No upcoming fixtures available.")
            return
        await message.answer("\U0001f3af *Choose a match to track:*",
                            parse_mode="Markdown", reply_markup=_fixture_keyboard(available))

    # ── /bet /ref /bantr ──

    async def cmd_bet(self, message: types.Message, parsed_args: list[str] | None = None) -> None:
        engine = self.container.engine
        store = self.container.store
        payments = self.container.payments
        nlu = self.container.nlu
        chat_id = message.chat.id
        username = self._username(message)

        args = parsed_args if parsed_args is not None else (message.text.split()[1:] if message.text else [])
        if len(args) < 3:
            player_market_names = ", ".join(_fmt_market(m) for m in PLAYER_MARKET_VALUES)
            await self._reply(message,
                f"Usage: /bet @user <market> <amount> [team|player]\n"
                f"Standard: {', '.join(_fmt_market(m) for m in ['next_goal', 'next_card', 'next_corner', 'match_winner'])}\n"
                f"Player: {player_market_names}\n"
                "  /bet @alice next_goal 50\n"
                "  /bet @bob match_winner 100 France\n"
                "  /bet @alice hat_trick 50 Mbappe")
            return

        fid = engine.chat_fixtures.get(chat_id)
        if not fid:
            await self._reply(message, "No fixture tracked. Use /fixtures to pick one first.")
            return

        opponent, market_str, amount_str = args[0], args[1], args[2]
        raw_extra = " ".join(args[3:]) if len(args) > 3 else None

        amount_str = amount_str.lstrip("$")
        try:
            amount = float(amount_str)
        except ValueError:
            await self._reply(message, "Amount must be a number (e.g. 50 or $50).")
            return

        if market_str not in VALID_MARKETS:
            if market_str in PLAYER_MARKETS:
                market_str = PLAYER_MARKETS[market_str]
            else:
                await self._reply(message, f"Unknown market. Use: {', '.join(VALID_MARKETS)}")
                return

        resolved_team, player_name, player_normative_id, player_display, team_note = None, None, None, None, ""
        is_player_market = market_str in PLAYER_MARKET_VALUES

        if raw_extra:
            if market_str == MARKET_MATCH_WINNER:
                resolved_team = raw_extra
                team_note = f"\nBacking: {resolved_team} to win"
            elif is_player_market:
                info = engine.fixture_info.get(fid, {})
                matches = engine.resolve_player_name(fid, raw_extra)
                if len(matches) == 1:
                    p = matches[0]
                    player_name = raw_extra
                    player_normative_id = p.get("normative_id")
                    player_display = p.get("match_display", player_name)
                    team_name_v = p.get("team_name", "?")
                    resolved_team = "team_1" if team_name_v == info.get("home") else "team_2"
                    team_note = f"\n{player_display} ({team_name_v})"
                    logger.info("player_resolved", input=raw_extra, display=player_display, nid=player_normative_id)
                elif len(matches) > 1:
                    top = matches[:5]
                    lines = [f"Multiple players match '{raw_extra}':\n"]
                    for p in top:
                        lines.append(f"\u2022 {p['match_display']} ({p.get('team_name', '?')})")
                    lines.append("\nReply with the full name to place your bet.")
                    await self._reply(message, "\n".join(lines))
                    return
                else:
                    info = engine.fixture_info.get(fid, {})
                    resolved = await nlu.resolve_player_team(raw_extra, info)
                    if resolved:
                        resolved_team = resolved
                        team_name_v = info.get("home") if resolved == "home" else info.get("away", "?")
                        player_name = raw_extra
                        player_display = raw_extra
                        team_note = f"\n{player_name} \u2192 {team_name_v} (AI-resolved)"
                    else:
                        resolved_team = raw_extra
                        team_note = f"\nResolves on: {resolved_team}"
            else:
                info = engine.fixture_info.get(fid, {})
                resolved = await nlu.resolve_player_team(raw_extra, info)
                if resolved:
                    resolved_team = resolved
                    team_name_v = info.get("home") if resolved == "home" else info.get("away", "?")
                    player_name = raw_extra
                    team_note = f"\n{player_name} \u2192 {team_name_v} (AI-resolved)"
                else:
                    resolved_team = raw_extra
                    team_note = f"\nResolves on: {resolved_team}"

        bet = store.create_bet({"chat_id": chat_id, "creator": username, "opponent": opponent,
            "market": market_str, "fixture_id": fid, "amount": amount,
            "team": resolved_team, "player": player_name,
            "player_normative_id": player_normative_id,
            "player_display": player_display or player_name,
            "player_market": market_str if is_player_market else None,
            "confirmed_events": 0})
        engine.active_bets[bet["id"]] = bet

        try:
            pay_req = await payments.generate_payment_request(bet)
            store.update_bet(bet["id"], {"payment_reference": pay_req["reference"]})
            engine.active_bets[bet["id"]]["payment_reference"] = pay_req["reference"]
            tracked = self._tracked_label(chat_id) or "?"
            resolve_note = "Resolves at full time — winner takes all." if market_str == MARKET_MATCH_WINNER else ""
            msg = (f"{opponent} \U0001f525 {username} challenges you!\n"
                   f"{tracked} | {market_str} | Stake: {amount}"
                   f"{team_note}\n{resolve_note}\n\n"
                   f"\U0001f4b3 {username}: {pay_req['transaction_request_url']}\n\n"
                   f"Accept: /call <code>{bet['id'][:4]}</code>")
            await message.answer(msg, parse_mode="HTML")
        except Exception as e:
            await self._reply(message, f"Bet created but payment setup failed: {e}")

    # ── /call ──

    async def cmd_call(self, message: types.Message) -> None:
        engine = self.container.engine
        store = self.container.store
        payments = self.container.payments
        chat_id = message.chat.id
        username = self._username(message)
        args = message.text.split()[1:] if message.text else []
        if not args:
            await self._reply(message, "Usage: /call <betId>")
            return
        partial = args[0].strip().lower()
        entry = None
        for bid, b in engine.active_bets.items():
            if bid.startswith(partial) and b.get("chat_id") == chat_id:
                entry = b; partial = bid; break
        if not entry or entry["status"] in (BET_STATUS_RESOLVED, BET_STATUS_VOID):
            await self._reply(message, "Bet not found.")
            return
        if entry.get("opponent") != username:
            await self._reply(message, f"Only {entry.get('opponent')} can accept.")
            return
        store.update_bet(partial, {"status": "called"})
        if partial in engine.active_bets:
            engine.active_bets[partial]["status"] = "called"
        try:
            opp_pay = await payments.generate_payment_request(entry, instruction="join_bet")
            await self._reply(message,
                f"{entry['creator']} \u2705 {username} accepted!\n"
                f"\U0001f4b3 {username}: {opp_pay['transaction_request_url']}",
                parse_mode="HTML")
        except Exception as e:
            await self._reply(message, f"\u2705 Accepted! (payment link failed: {e})")
        ref = entry.get("payment_reference")
        if ref:
            payments.watch_for_deposit(ref, lambda confirmed: self._on_deposit(chat_id, partial, confirmed))

    # ── /leaderboard ──

    async def cmd_leaderboard(self, message: types.Message) -> None:
        store = self.container.store
        stats = store.get_leaderboard(message.chat.id)
        entries = sorted(stats.items(), key=lambda x: x[1]["wins"], reverse=True)
        if not entries:
            await self._reply(message, "No resolved bets yet. Start the banter with /bet!")
            return
        lines = ["\U0001f3c6 *Leaderboard*"]
        for user, s in entries:
            lines.append(f"{user}: {s['wins']}W — {s['losses']}L")
        await self._reply(message, "\n".join(lines), parse_mode="Markdown")

    # ── Callback handler ──

    async def handle_callback(self, callback: CallbackQuery) -> None:
        try:
            await callback.answer()
        except Exception:
            pass
        data = callback.data or ""

        if data == "menu:fixtures":
            engine = self.container.engine
            available = engine.fixture_info.values()
            if not available:
                await callback.message.edit_text("No upcoming fixtures available.", reply_markup=_inline_menu())
                return
            tracked = engine.chat_fixtures.get(callback.message.chat.id)
            lines = ["\U0001f4c5 *Available fixtures*\n_Tap a match to track it:_"]
            for f in available:
                tag = "  \u2705 tracked" if f["id"] == tracked else ""
                lines.append(_fixture_label(f) + tag)
            await callback.message.edit_text("\n".join(lines), parse_mode="Markdown",
                                            reply_markup=_fixture_keyboard(available))
        elif data.startswith("menu:track:"):
            fid = data.split(":", 2)[2]
            engine = self.container.engine
            info = engine.fixture_info.get(fid)
            if info:
                engine.track_fixture_for_chat(callback.message.chat.id, fid)
                f = {"home": info["home"], "away": info["away"]}
                await callback.message.edit_text(
                    f"\U0001f3ae Tracking *{_fixture_label(f)}*\nPlace your bets with /bet!",
                    parse_mode="Markdown", reply_markup=_inline_menu())
            else:
                await callback.message.edit_text("Fixture not available.", reply_markup=_inline_menu())
        elif data == "menu:leaderboard":
            stats = self.container.store.get_leaderboard(callback.message.chat.id)
            entries = sorted(stats.items(), key=lambda x: x[1]["wins"], reverse=True)
            if not entries:
                await callback.message.edit_text("No resolved bets yet.", reply_markup=_inline_menu())
                return
            lines = ["\U0001f3c6 *Leaderboard*"]
            for user, s in entries:
                lines.append(f"{user}: {s['wins']}W — {s['losses']}L")
            await callback.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=_inline_menu())
        elif data == "menu:help":
            await self._help_callback(callback)
        elif data == "menu:start":
            await callback.message.edit_text(
                "\U0001f3c6 *Welcome to BanterBot!*\n\n"
                "Turn your group chat into a live World Cup betting arena.\n\n"
                "\u26bd Track matches in real time\n"
                "\U0001f91d Challenge friends with bets\n"
                "\U0001f50d Verify results with on-chain proofs\n"
                "\U0001f9e0 Or just chat naturally.",
                parse_mode="Markdown", reply_markup=_inline_menu())
        elif data.startswith("menu:bet_build:"):
            market = data.split(":", 2)[2]
            player_markets = {"hat_trick", "first_scorer", "two_goals", "player_card", "scores", "clean_sheet"}
            if market in player_markets:
                await callback.message.edit_text(
                    f"*Market:* {market}\n\n"
                    "Now type:\n"
                    f"`/bet @opponent {market} <amount> <player_name>`\n\n"
                    f"Example: `/bet @alice {market} 50 Mbappe`\n\n"
                    "The bot will match the player from the live fixture roster.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="\U0001f519 Back", callback_data="menu:start")]]))
            else:
                await callback.message.edit_text(
                    f"Market: {market}\n\nNow type:\n"
                    f"/bet @opponent {market} &lt;amount&gt; [team]\n\n"
                    f"Example: /bet @alice {market} 50 France",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="\U0001f519 Back", callback_data="menu:start")]]))

    async def handle_poll_vote(self, callback: CallbackQuery) -> None:
        from app.services.betting.polls import poll_manager
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        try: await callback.answer()
        except Exception: pass

        data = callback.data or ""
        parts = data.split(":")
        if len(parts) < 4:
            return
        poll_id, vote = parts[2], parts[3]
        poll = poll_manager.get(poll_id)
        if not poll or poll.resolved:
            try: await callback.message.edit_text("Poll closed.", reply_markup=None)
            except Exception: pass
            return

        username = self._username(callback)
        if not poll.vote(username, vote == "yes"):
            try: await callback.answer("Already voted!", show_alert=True)
            except Exception: pass
            return

        if poll.is_consensus():
            poll_manager.resolve(poll_id)
            engine = self.container.engine
            bet = engine.active_bets.get(poll.bet_id)
            status = ""
            if bet and poll.result:
                confirmed = bet.get("confirmed_events", 0) + 1
                engine.active_bets[poll.bet_id]["confirmed_events"] = confirmed
                required = PLAYER_MARKET_REQUIRED_EVENTS.get(bet.get("player_market", "scores"), 1)
                status = f"Progress: {confirmed}/{required}"
                if confirmed >= required:
                    self.container.store.update_bet(poll.bet_id,
                        {"status": BET_STATUS_RESOLVED, "winner": bet["creator"]})
                    engine.active_bets.pop(poll.bet_id, None)
                    status = "\U0001f3c6 Won!"
            else:
                status = "\u274c Not confirmed"

            player_label = poll.player
            if bet:
                player_label = bet.get("player_display", bet.get("player", poll.player))
            await callback.message.edit_text(
                f"\u26bd {poll.event_description} for {player_label}\n"
                f"{status}", reply_markup=None)
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"\u2705 Yes ({len(poll.votes_yes)})",
                    callback_data=f"poll:vote:{poll_id}:yes"),
                 InlineKeyboardButton(text=f"\u274c No ({len(poll.votes_no)})",
                    callback_data=f"poll:vote:{poll_id}:no")],
            ])
            try: await callback.message.edit_reply_markup(reply_markup=kb)
            except Exception: pass

    # ── NLU routing (DeepSeek last resort) ──

    async def handle_nlu(self, message: types.Message) -> None:
        text = message.text or ""
        text = re.sub(r'@\w+bot\b', '', text, flags=re.IGNORECASE).strip()
        if not text or text.startswith("/"):
            return

        engine = self.container.engine

        # ── Tier 1: Reply keyboard buttons (instant, no AI) ──
        if text in KEYBOARD_MAP:
            cmd = KEYBOARD_MAP[text]
            logger.info("route_keyboard", handler=cmd, text=text)
            if cmd == "fixtures": await self.cmd_fixtures(message)
            elif cmd == "track": await self.cmd_track(message)
            elif cmd == "leaderboard": await self.cmd_leaderboard(message)
            elif cmd == "help": await self.cmd_help(message)
            elif cmd == "bet":
                await self._reply(message, "Use /bet @user <market> <amount> to challenge someone!")
            return

        # ── Tier 2: Known aliases (instant, no AI) ──
        lower = text.strip().lower()
        if lower in ALIASES:
            cmd = ALIASES[lower]
            logger.info("route_alias", handler=cmd, text=text)
            if cmd == "fixtures": await self.cmd_fixtures(message)
            elif cmd == "track": await self.cmd_track(message)
            elif cmd == "leaderboard": await self.cmd_leaderboard(message)
            elif cmd == "help": await self.cmd_help(message)
            return

        # ── Everything else bet-like: unified flow with ack message ──
        bet_triggers = ("bet", "wager", "challenge", "stake", "$", "win", "lose",
                        "beat", "score", "card", "corner", "goal", "ref", "bantr",
                        "hat trick", "hattrick", "scores", "scoring", "booked",
                        "red card", "yellow card", "penalty", "brace", "clean sheet",
                        "cleansheet", "first goal", "first scorer", "two goals")
        cmd_triggers = ("fixture", "match", "leaderboard", "ranking", "track", "help")
        looks_like_bet = any(kw in text.lower() for kw in bet_triggers)
        looks_like_cmd = any(kw in text.lower() for kw in cmd_triggers)

        if not looks_like_bet and not looks_like_cmd:
            return

        # ── Show acknowledgment, try to resolve ──
        ack = await message.answer(
            "\u23f3 Reading your bet...",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f6a8 Skip — build manually", callback_data="menu:bet_build:next_goal")],
            ]),
        )

        # Try deterministic parser first
        parsed = _parse_bet(text)
        if parsed and parsed.get("opponent") and parsed.get("amount"):
            logger.info("route_deterministic_bet", params=parsed)
            try:
                await ack.delete()
            except Exception:
                pass
            args = [parsed["opponent"], parsed.get("market") or "next_goal", parsed["amount"]]
            if parsed.get("player"): args.append(parsed["player"])
            elif parsed.get("team"): args.append(parsed["team"])
            await self.cmd_bet(message, parsed_args=args)
            return

        # Try DeepSeek with 25s timeout
        fixtures_ctx = [{"id": fid, **info} for fid, info in engine.fixture_info.items()]
        logger.info("route_deepseek", text=text[:60])
        try:
            parsed_ai = await _asyncio.wait_for(
                self.container.nlu.parse(text, fixtures_ctx), timeout=25)
        except _asyncio.TimeoutError:
            parsed_ai = {"intent": "unknown", "params": {}, "confidence": 0}

        intent = parsed_ai.get("intent", "unknown")
        params = parsed_ai.get("params", {})
        confidence = parsed_ai.get("confidence", 0)

        if intent == "bet" and params.get("opponent") and params.get("market") and params.get("amount") and confidence >= 0.4:
            try: await ack.delete()
            except Exception: pass
            args = [params["opponent"], params["market"], params["amount"]]
            if params.get("player"): args.append(params["player"])
            elif params.get("team"): args.append(params["team"])
            await self.cmd_bet(message, parsed_args=args)
            return

        # Couldn't resolve — show manual builder in the ack message
        opponent_hint = ""
        if params.get("opponent"):
            opponent_hint = f"\nOpponent: {params['opponent']}"
        await ack.edit_text(
            f"\U0001f4b0 *Build your bet*{opponent_hint}\nTap a market:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="next_goal", callback_data="menu:bet_build:next_goal"),
                 InlineKeyboardButton(text="next_card", callback_data="menu:bet_build:next_card")],
                [InlineKeyboardButton(text="next_corner", callback_data="menu:bet_build:next_corner"),
                 InlineKeyboardButton(text="match_winner", callback_data="menu:bet_build:match_winner")],
                [InlineKeyboardButton(text="hat_trick (player)", callback_data="menu:bet_build:hat_trick"),
                 InlineKeyboardButton(text="first_scorer (player)", callback_data="menu:bet_build:first_scorer")],
                [InlineKeyboardButton(text="two_goals (player)", callback_data="menu:bet_build:two_goals"),
                 InlineKeyboardButton(text="player_card (player)", callback_data="menu:bet_build:player_card")],
                [InlineKeyboardButton(text="scores (player)", callback_data="menu:bet_build:scores"),
                 InlineKeyboardButton(text="clean_sheet (player)", callback_data="menu:bet_build:clean_sheet")],
                [InlineKeyboardButton(text="\U0001f519 Cancel", callback_data="menu:start")],
            ]),
        )

    def _on_deposit(self, chat_id: int, bet_id: str, confirmed: bool) -> None:
        if not confirmed:
            return
        self.container.store.update_bet(bet_id, {"status": "funded"})
        if bet_id in self.container.engine.active_bets:
            self.container.engine.active_bets[bet_id]["status"] = "funded"
        import asyncio
        asyncio.ensure_future(self.send_message(chat_id,
            f"\U0001f4b0 Bet funded. Waiting for the next live event..."))

    # ── Lifecycle ──

    def _register_handlers(self) -> None:
        r = self._router
        r.message.register(self.cmd_start, Command("start"))
        r.message.register(self.cmd_help, Command("help"))
        r.message.register(self.cmd_fixtures, Command("fixtures"))
        r.message.register(self.cmd_track, Command("track"))
        r.message.register(self.cmd_bet, Command("bet"))
        r.message.register(self.cmd_bet, Command("ref"))
        r.message.register(self.cmd_bet, Command("bantr"))
        r.message.register(self.cmd_call, Command("call"))
        r.message.register(self.cmd_leaderboard, Command("leaderboard"))
        r.callback_query.register(self.handle_callback, F.data.startswith("menu:"))
        r.callback_query.register(self.handle_poll_vote, F.data.startswith("poll:vote:"))

        @r.message()
        async def route_all(msg: types.Message):
            text = msg.text or ""
            if text.startswith("/"):
                return
            if msg.chat:
                logger.info("msg", chat_id=msg.chat.id, text=text[:60])
            await self.handle_nlu(msg)

    async def start_async(self) -> None:
        self.bot = Bot(token=settings.telegram_bot_token)
        self.dp = Dispatcher()
        self.dp.include_router(self._router)
        self._register_handlers()
        logger.info("telegram_bot_starting", debug=settings.app_debug)

        try:
            me = await self.bot.get_me()
            settings.telegram_bot_username = me.username or settings.telegram_bot_username
            logger.info("bot_identity", username=settings.telegram_bot_username, id=me.id)
        except Exception:
            logger.warning("bot_get_me_failed", fallback=settings.telegram_bot_username)

        await self.bot.delete_webhook(drop_pending_updates=False)

        if settings.app_debug:
            await self.dp.start_polling(self.bot, handle_signals=False)
        else:
            url = f"{settings.app_webhook_url.rstrip('/')}/webhook"
            if not settings.app_webhook_url:
                logger.error("webhook_url_not_set", error="APP_WEBHOOK_URL is empty, webhook cannot be registered")
            else:
                try:
                    await self.bot.set_webhook(url=url, drop_pending_updates=True)
                    logger.info("webhook_registered", url=url)
                except Exception as exc:
                    logger.error("webhook_registration_failed", url=url, error=str(exc))

    async def stop_async(self) -> None:
        if self.bot:
            await self.bot.delete_webhook(drop_pending_updates=True)
        if self.dp:
            await self.dp.stop_polling()

    async def feed_update(self, update: types.Update) -> None:
        if self.bot and self.dp:
            await self.dp.feed_webhook_update(self.bot, update)
