from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup,
    KeyboardButton, CallbackQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.core.config import settings
from app.core.constants import (
    VALID_MARKETS, UPCOMING_FIXTURES,
    BET_STATUS_RESOLVED, BET_STATUS_VOID, flag_for,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

HELP_TEXT = """\U0001f4d6 *Available Commands*

\U0001f4c5 /fixtures — View upcoming matches
\U0001f3af /track — Select which fixture to bet on
\U0001f4b0 /bet @user <market> <amount> \\[player/team] — Challenge someone
\u2705 /call <bet_id> — Accept a pending bet
\U0001f3c6 /leaderboard — View rankings

\U0001f9e0 *Natural Language*
You can also just chat naturally — I understand:

\u2022 "Bet 50 on the next goal"
\u2022 "Show today's matches"
\u2022 "Track the France game"
\u2022 "Challenge @alex to 20 on the next corner"
\u2022 "Accept bet abc123"

I'll figure it out and do the right thing."""

REPLY_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="\u26bd Fixtures"), KeyboardButton(text="\U0001f3af Track")],
        [KeyboardButton(text="\U0001f4b0 Bet"), KeyboardButton(text="\U0001f3c6 Leaderboard")],
        [KeyboardButton(text="\u2753 Help")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Tap a button or type naturally...",
)


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
            InlineKeyboardButton(
                text="\U0001f916 Add to Group",
                url=f"https://t.me/{settings.telegram_bot_username}?startgroup=start",
            ),
        ],
    ])


def _fixture_label(f: dict) -> str:
    hf = flag_for(f["home"])
    af = flag_for(f["away"])
    return f"{hf} {f['home']} vs {af} {f['away']}"


def _fixture_keyboard(available: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for f in available:
        label = _fixture_label(f)
        builder.button(text=label, callback_data=f"menu:track:{f['id']}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="\U0001f519 Back", callback_data="menu:start"))
    return builder.as_markup()


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
            "\U0001f9e0 Or just chat naturally \u2014 I understand plain English.",
            parse_mode="Markdown",
            reply_markup=_inline_menu(),
        )

    # ── /help ──

    async def cmd_help(self, message: types.Message) -> None:
        await message.answer(HELP_TEXT, parse_mode="Markdown")

    async def _help_callback(self, callback: CallbackQuery) -> None:
        await callback.message.edit_text(HELP_TEXT, parse_mode="Markdown", reply_markup=_inline_menu())

    # ── /fixtures ──

    async def cmd_fixtures(self, message: types.Message) -> None:
        engine = self.container.engine
        available = [f for f in UPCOMING_FIXTURES if f["id"] in engine.fixture_info]
        if not available:
            await self._reply(message, "No upcoming fixtures available.")
            return

        tracked = engine.chat_fixtures.get(message.chat.id)
        lines = ["\U0001f4c5 *Available fixtures*\n_Tap a match to track it:_"]
        for f in available:
            tag = "  \u2705 tracked" if f["id"] == tracked else ""
            lines.append(_fixture_label(f) + tag)

        await message.answer(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=_fixture_keyboard(available),
        )

    # ── /track ──

    async def cmd_track(self, message: types.Message, command=None) -> None:
        engine = self.container.engine
        available = [f for f in UPCOMING_FIXTURES if f["id"] in engine.fixture_info]
        if not available:
            await self._reply(message, "No upcoming fixtures available.")
            return

        await message.answer(
            "\U0001f3af *Choose a match to track:*",
            parse_mode="Markdown",
            reply_markup=_fixture_keyboard(available),
        )

    # ── /bet ──

    async def cmd_bet(self, message: types.Message) -> None:
        engine = self.container.engine
        store = self.container.store
        payments = self.container.payments
        nlu = self.container.nlu
        chat_id = message.chat.id
        username = self._username(message)

        args = message.text.split()[1:] if message.text else []
        if len(args) < 3:
            await self._reply(
                message,
                f"Usage: /bet @user <market> <amount> [player/team]\n"
                f"Markets: {', '.join(VALID_MARKETS)}\n"
                "Examples:\n  /bet @alice next_goal 50\n  /bet @bob next_card 100 Messi",
            )
            return

        fid = engine.chat_fixtures.get(chat_id)
        if not fid:
            await self._reply(message, "No fixture tracked. Use /fixtures to pick one first.")
            return

        opponent = args[0]
        market_str = args[1]
        amount_str = args[2]
        raw_extra = " ".join(args[3:]) if len(args) > 3 else None

        try:
            amount = float(amount_str)
        except ValueError:
            await self._reply(message, "Amount must be a number.")
            return

        if market_str not in VALID_MARKETS:
            await self._reply(message, f"Unknown market. Use: {', '.join(VALID_MARKETS)}")
            return

        resolved_team = None
        player_name = None
        team_note = ""

        if raw_extra:
            info = engine.fixture_info.get(fid, {})
            resolved = await nlu.resolve_player_team(raw_extra, info)
            if resolved:
                resolved_team = resolved
                home = info.get("home", "home")
                away = info.get("away", "away")
                team_name = home if resolved == "home" else away
                player_name = raw_extra
                team_note = f"\n{player_name} \u2192 {team_name} (AI-resolved)"
            else:
                resolved_team = raw_extra
                team_note = f"\nResolves on: {resolved_team}"

        bet = store.create_bet({
            "chat_id": chat_id, "creator": username, "opponent": opponent,
            "market": market_str, "fixture_id": fid, "amount": amount,
            "team": resolved_team, "player": player_name,
        })
        engine.active_bets[bet["id"]] = bet

        try:
            pay_req = await payments.generate_payment_request(bet)
            store.update_bet(bet["id"], {"payment_reference": pay_req["reference"]})
            engine.active_bets[bet["id"]]["payment_reference"] = pay_req["reference"]

            tracked = self._tracked_label(chat_id) or "?"
            msg = (
                f"\U0001f525 {username} challenges {opponent}!\n"
                f"{tracked} | {market_str} | Stake: {amount}"
                f"{team_note}\n\n"
                f"Accept with /call `{bet['id'][:4]}`\n"
                f"\U0001f4b3 Pay: {pay_req['transaction_request_url']}"
            )
            await self._reply(message, msg, parse_mode="Markdown")
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
            await self._reply(message, "Usage: /call <betId>  (the 4-character ID shown in the bet message)")
            return

        partial = args[0].strip().lower()
        entry = None
        for bid, b in engine.active_bets.items():
            if bid.startswith(partial) and b.get("chat_id") == chat_id:
                entry = b
                partial = bid
                break

        if not entry or entry["status"] in (BET_STATUS_RESOLVED, BET_STATUS_VOID):
            await self._reply(message, "Bet not found. Check the bet ID in the challenge message.")
            return

        if entry.get("opponent") != username:
            await self._reply(message, f"Only {entry.get('opponent')} can accept.")
            return

        store.update_bet(partial, {"status": "called"})
        if partial in engine.active_bets:
            engine.active_bets[partial]["status"] = "called"

        await self._reply(message, f"\u2705 {username} accepted the bet. It's locked. May the best banter win.")
        ref = entry.get("payment_reference")
        if ref:
            payments.watch_for_deposit(ref, lambda confirmed: self._on_deposit(chat_id, partial, confirmed))

    # ── /leaderboard ──

    async def cmd_leaderboard(self, message: types.Message) -> None:
        store = self.container.store
        chat_id = message.chat.id
        stats = store.get_leaderboard(chat_id)
        entries = sorted(stats.items(), key=lambda x: x[1]["wins"], reverse=True)
        if not entries:
            await self._reply(message, "No resolved bets yet. Start the banter with /bet!")
            return
        lines = ["\U0001f3c6 *Leaderboard*"]
        for user, s in entries:
            lines.append(f"{user}: {s['wins']}W \u2014 {s['losses']}L")
        await self._reply(message, "\n".join(lines), parse_mode="Markdown")

    # ── Callback handler ──

    async def handle_callback(self, callback: CallbackQuery) -> None:
        await callback.answer()
        data = callback.data or ""

        if data == "menu:fixtures":
            engine = self.container.engine
            available = [f for f in UPCOMING_FIXTURES if f["id"] in engine.fixture_info]
            if not available:
                await callback.message.edit_text("No upcoming fixtures available.", reply_markup=_inline_menu())
                return
            tracked = engine.chat_fixtures.get(callback.message.chat.id)
            lines = ["\U0001f4c5 *Available fixtures*\n_Tap a match to track it:_"]
            for f in available:
                tag = "  \u2705 tracked" if f["id"] == tracked else ""
                lines.append(_fixture_label(f) + tag)
            await callback.message.edit_text(
                "\n".join(lines),
                parse_mode="Markdown",
                reply_markup=_fixture_keyboard(available),
            )

        elif data.startswith("menu:track:"):
            fid = data.split(":", 2)[2]
            engine = self.container.engine
            info = engine.fixture_info.get(fid)
            if info:
                engine.chat_fixtures[callback.message.chat.id] = fid
                engine._ensure_tracked(fid)
                f = {"home": info["home"], "away": info["away"]}
                await callback.message.edit_text(
                    f"\U0001f3ae Tracking *{_fixture_label(f)}*\nPlace your bets with /bet!",
                    parse_mode="Markdown",
                    reply_markup=_inline_menu(),
                )
            else:
                await callback.message.edit_text("Fixture not available.", reply_markup=_inline_menu())

        elif data == "menu:leaderboard":
            store = self.container.store
            stats = store.get_leaderboard(callback.message.chat.id)
            entries = sorted(stats.items(), key=lambda x: x[1]["wins"], reverse=True)
            if not entries:
                await callback.message.edit_text("No resolved bets yet.", reply_markup=_inline_menu())
                return
            lines = ["\U0001f3c6 *Leaderboard*"]
            for user, s in entries:
                lines.append(f"{user}: {s['wins']}W \u2014 {s['losses']}L")
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
                parse_mode="Markdown",
                reply_markup=_inline_menu(),
            )

    # ── NLU handler ──

    async def handle_nlu(self, message: types.Message) -> None:
        text = message.text or ""
        if text.startswith("/"):
            return

        engine = self.container.engine
        fixtures_ctx = [{"id": fid, **info} for fid, info in engine.fixture_info.items()]
        parsed = await self.container.nlu.parse(text, fixtures_ctx)
        if parsed.get("confidence", 0) < 0.5:
            return

        intent = parsed.get("intent", "unknown")
        params = parsed.get("params", {})

        try:
            if intent == "fixtures":
                await self.cmd_fixtures(message)
            elif intent == "track":
                fid = params.get("fixtureId", "")
                if fid:
                    engine = self.container.engine
                    info = engine.fixture_info.get(fid)
                    if info:
                        engine.chat_fixtures[message.chat.id] = fid
                        engine._ensure_tracked(fid)
                        f = {"home": info["home"], "away": info["away"]}
                        await self._reply(message, f"\U0001f3ae Tracking *{_fixture_label(f)}*", parse_mode="Markdown")
            elif intent == "bet":
                opponent = params.get("opponent", params.get("user", ""))
                market = params.get("market", "")
                amount = params.get("amount", "")
                if opponent and market and amount:
                    parts = [opponent, market, amount]
                    player = params.get("player", "")
                    if player:
                        parts.append(player)
                    message.text = "/bet " + " ".join(parts)
                    await self.cmd_bet(message)
                else:
                    await self._reply(message, "Couldn't parse that. Try: /bet @user next_goal 50")
            elif intent == "call":
                bet_id = params.get("betId", params.get("id", ""))
                if bet_id:
                    message.text = f"/call {bet_id}"
                    await self.cmd_call(message)
            elif intent == "leaderboard":
                await self.cmd_leaderboard(message)
        except Exception as e:
            logger.error("nlu_handler_error", error=str(e))

    def _on_deposit(self, chat_id: int, bet_id: str, confirmed: bool) -> None:
        if not confirmed:
            return
        self.container.store.update_bet(bet_id, {"status": "funded"})
        if bet_id in self.container.engine.active_bets:
            self.container.engine.active_bets[bet_id]["status"] = "funded"
        import asyncio
        asyncio.ensure_future(
            self.send_message(chat_id, f"\U0001f4b0 Bet funded. Waiting for the next live event...")
        )

    # ── Lifecycle ──

    def _register_handlers(self) -> None:
        r = self._router
        r.message.register(self.cmd_start, Command("start"))
        r.message.register(self.cmd_help, Command("help"))
        r.message.register(self.cmd_fixtures, Command("fixtures"))
        r.message.register(self.cmd_track, Command("track"))
        r.message.register(self.cmd_bet, Command("bet"))
        r.message.register(self.cmd_call, Command("call"))
        r.message.register(self.cmd_leaderboard, Command("leaderboard"))
        r.callback_query.register(self.handle_callback, F.data.startswith("menu:"))
        r.message.register(self.handle_nlu, F.text)

    async def start_async(self) -> None:
        self.bot = Bot(token=settings.telegram_bot_token)
        self.dp = Dispatcher()
        self.dp.include_router(self._router)
        self._register_handlers()
        logger.info("telegram_bot_starting", debug=settings.app_debug)
        if settings.app_debug:
            await self.dp.start_polling(self.bot)
        else:
            url = f"{settings.app_webhook_url.rstrip('/')}/webhook"
            await self.bot.set_webhook(url=url, drop_pending_updates=True)
            logger.info("webhook_registered", url=url)

    async def stop_async(self) -> None:
        if not settings.app_debug and self.bot:
            await self.bot.delete_webhook(drop_pending_updates=True)
        if self.dp:
            await self.dp.stop_polling()

    async def feed_update(self, update: types.Update) -> None:
        if self.bot and self.dp:
            await self.dp.feed_webhook_update(self.bot, update)
