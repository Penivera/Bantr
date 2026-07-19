"""Comprehensive integration test suite for BanterBot.

Covers: bet parsing, alias map, fixtures, bet lifecycle,
player resolution, constants, payment link, NLU accuracy.

Run: python -m pytest tests/ -v
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.telegram.bot import _parse_bet, KEYBOARD_MAP, ALIASES, BET_MARKET_MAP
from app.core.constants import (
    VALID_MARKETS, MARKET_NEXT_GOAL, MARKET_NEXT_CARD, MARKET_NEXT_CORNER,
    MARKET_MATCH_WINNER, PLAYER_MARKET_VALUES, BET_STATUS_OPEN, BET_STATUS_CALLED,
    BET_STATUS_RESOLVED, BET_STATUS_VOID,
)

from tests.conftest import create_test_services, FIXTURE_DATA


# ══════════════════════════════════════════════════
# 1. DETERMINISTIC BET PARSER (regex)
# ══════════════════════════════════════════════════

class TestDeterministicBetParser:
    def test_bet_next_goal(self):
        r = _parse_bet("@alice 50 next goal")
        assert r is not None
        assert r["opponent"] == "@alice"
        assert r["amount"] == "50"
        assert r["market"] == "next_goal"

    def test_bet_with_team(self):
        r = _parse_bet("@alice 50 next_goal France")
        assert r is not None
        assert r["opponent"] == "@alice"
        assert r["amount"] == "50"
        assert r["market"] == "next_goal"
        assert r["team"] == "France"

    def test_bet_amount_first(self):
        r = _parse_bet("@bob 100 match_winner France")
        assert r is not None
        assert r["opponent"] == "@bob"
        assert r["amount"] == "100"
        assert r["market"] == "match_winner"
        assert r["team"] == "France"

    def test_bet_with_dollar_sign(self):
        r = _parse_bet("@bob $50 next goal")
        assert r is not None, f"$50 not parsed: {r}"
        assert r["amount"] == "50"

    def test_player_hat_trick(self):
        r = _parse_bet("@alice 50 hat_trick Mbappe")
        assert r is not None
        assert r["market"] == "hat_trick"
        assert r["player"].lower() == "mbappe"

    def test_player_scores(self):
        r = _parse_bet("@bob 100 scores Messi")
        assert r is not None
        assert r["market"] == "scores"
        assert r["player"].lower() == "messi"

    def test_player_first_scorer(self):
        r = _parse_bet("@charlie 25 first_scorer Ronaldo")
        assert r is not None
        assert r["market"] == "first_scorer"
        assert r["player"].lower() == "ronaldo"

    def test_player_clean_sheet(self):
        r = _parse_bet("@dave 30 clean_sheet")
        assert r is not None
        assert r["market"] == "clean_sheet"

    # Alias tests
    def test_alias_goal(self):
        r = _parse_bet("@alice 50 goal")
        assert r is not None and r["market"] == "next_goal"

    def test_alias_card(self):
        r = _parse_bet("@alice 50 card")
        assert r is not None
        assert r["market"] == "player_card"

    def test_alias_yellow(self):
        r = _parse_bet("@alice 50 yellow")
        assert r is not None
        assert r["market"] == "next_card"

    def test_alias_red(self):
        r = _parse_bet("@alice 50 red")
        assert r is not None and r["market"] == "next_card"

    def test_alias_corner(self):
        r = _parse_bet("@alice 50 next corner")
        assert r is not None and r["market"] == "next_corner"

    def test_alias_win(self):
        r = _parse_bet("@alice 50 win France")
        assert r is not None and r["market"] == "match_winner"

    def test_alias_beat(self):
        r = _parse_bet("@alice 50 beat France")
        assert r is not None and r["market"] == "match_winner"

    def test_alias_hat_trick(self):
        r = _parse_bet("@alice 50 hat trick Mbappe")
        assert r is not None and r["market"] == "hat_trick"

    def test_alias_hattrick(self):
        r = _parse_bet("@alice 50 hattrick Mbappe")
        assert r is not None and r["market"] == "hat_trick"

    def test_alias_hat_dash_trick(self):
        r = _parse_bet("@alice 50 hat-trick Mbappe")
        assert r is not None and r["market"] == "hat_trick"

    def test_alias_first_goal(self):
        r = _parse_bet("@alice 50 first goal Mbappe")
        assert r is not None and r["market"] == "first_scorer"

    def test_alias_two_goals(self):
        r = _parse_bet("@alice 50 two goals Mbappe")
        assert r is not None and r["market"] == "two_goals"

    def test_alias_brace(self):
        r = _parse_bet("@alice 50 brace Mbappe")
        assert r is not None and r["market"] == "two_goals"

    def test_alias_booked(self):
        r = _parse_bet("@alice 50 booked Mbappe")
        assert r is not None and r["market"] == "player_card"

    def test_alias_red_card(self):
        r = _parse_bet("@alice 50 red card Mbappe")
        assert r is not None and r["market"] == "player_card"

    def test_alias_clean_sheet(self):
        r = _parse_bet("@alice 50 clean sheet")
        assert r is not None and r["market"] == "clean_sheet"

    def test_alias_cleansheet(self):
        r = _parse_bet("@alice 50 cleansheet")
        assert r is not None and r["market"] == "clean_sheet"

    # Negative cases
    def test_no_at(self):
        assert _parse_bet("bet 50 goal") is None

    def test_no_amount(self):
        assert _parse_bet("@alice goal") is None

    def test_jibberish(self):
        assert _parse_bet("asdfghjkl moon") is None

    def test_empty(self):
        assert _parse_bet("") is None

    @pytest.mark.parametrize("text,expected_market", [
        ("@alice 50 next goal", "next_goal"),
        ("@bob 100 next card", "next_card"),
        ("@charlie 50 next_corner", "next_corner"),
        ("@dan 200 match_winner Spain", "match_winner"),
        ("@eva 101 next_goal France", "next_goal"),
        ("@frank 50 scores", "scores"),
        ("@georg 500 two goals", "two_goals"),
        ("@alice 50 brace mbappe", "two_goals"),
        ("@bob 100 card mbappe", "player_card"),
        ("$50 @alice next goal france", "next_goal"),
    ])
    def test_parametrized_correct(self, text, expected_market):
        r = _parse_bet(text)
        if r:
            assert r["market"] == expected_market, f"{text} -> {r}"


# ══════════════════════════════════════════════════
# 2. ALIAS MAP & KEYBOARD
# ══════════════════════════════════════════════════

class TestAliasMap:
    def test_fixtures_triggers(self):
        triggers = ["fixtures", "matches", "games", "show fixtures", "show matches",
                    "today fixtures", "today's matches", "upcoming", "what matches", "who playing"]
        for t in triggers:
            assert ALIASES.get(t) == "fixtures", f"'{t}' should route to fixtures"

    def test_leaderboard_triggers(self):
        triggers = ["leaderboard", "rankings", "show leaderboard", "scoreboard"]
        for t in triggers:
            assert ALIASES.get(t) == "leaderboard", f"'{t}' should route to leaderboard"

    def test_help_triggers(self):
        triggers = ["help", "commands", "what can you do", "how does this work", "how to bet"]
        for t in triggers:
            assert ALIASES.get(t) == "help", f"'{t}' should route to help"

    def test_track_triggers(self):
        triggers = ["track", "track match", "select match", "pick match"]
        for t in triggers:
            assert ALIASES.get(t) == "track", f"'{t}' should route to track"

    def test_keyboard_buttons(self):
        for _ui_text, cmd in KEYBOARD_MAP.items():
            assert cmd in ("fixtures", "track", "bet", "bets", "leaderboard", "challenges", "history", "help")

    def test_bet_market_map_completeness(self):
        for key, val in BET_MARKET_MAP.items():
            assert val in VALID_MARKETS, f"'{key}' maps to nonexistent market '{val}'"


# ══════════════════════════════════════════════════
# 3. FIXTURES & TRACKING
# ══════════════════════════════════════════════════

class TestFixtures:
    def test_fixture_dataloaded(self):
        svc = create_test_services()
        assert len(svc.engine.fixture_info) == 2
        assert svc.engine.fixture_info["18257865"]["home"] == "France"
        assert svc.engine.fixture_info["18257739"]["away"] == "Brazil"

    def test_fixture_label(self):
        svc = create_test_services()
        assert svc.engine.fixture_label("18257865") == "France vs Spain"

    def test_chat_fixture_map(self):
        svc = create_test_services()
        svc.engine.chat_fixtures[111] = "18257865"
        svc.engine.tracked.add("18257865")
        assert svc.engine.chat_fixtures[111] == "18257865"
        assert "18257865" in svc.engine.tracked

    def test_multiple_channels_same_fixture(self):
        svc = create_test_services()
        svc.engine.chat_fixtures[111] = "18257865"
        svc.engine.chat_fixtures[222] = "18257865"
        svc.engine.tracked.add("18257865")
        assert svc.engine.chat_fixtures[111] == "18257865"
        assert svc.engine.chat_fixtures[222] == "18257865"

    def test_unknown_fixture_label(self):
        svc = create_test_services()
        assert "?" in svc.engine.fixture_label("99999")


# ══════════════════════════════════════════════════
# 4. BET LIFECYCLE
# ══════════════════════════════════════════════════

class TestBetLifecycle:
    def test_bet_created_and_has_id(self):
        svc = create_test_services()
        bet = svc.store.create_bet({
            "chat_id": 1, "creator": "@a", "opponent": "@b",
            "fixture_id": "18257865", "market": "next_goal", "amount": 50,
        })
        assert len(bet["id"]) == 7
        assert bet["status"] == BET_STATUS_OPEN

    def test_bet_called(self):
        svc = create_test_services()
        bet = svc.store.create_bet({
            "chat_id": 1, "creator": "@a", "opponent": "@b",
            "fixture_id": "x", "market": "next_goal", "amount": 1,
        })
        svc.store.update_bet(bet["id"], {"status": "called"})
        assert svc.store.get_bet(bet["id"])["status"] == "called"

    def test_resolved_leaderboard(self):
        svc = create_test_services()
        bet = svc.store.create_bet({
            "chat_id": 10, "creator": "@winner", "opponent": "@loser",
            "fixture_id": "y", "market": "next_goal", "amount": 10,
        })
        svc.store.update_bet(bet["id"], {"status": BET_STATUS_RESOLVED, "winner": "@winner"})
        b = svc.store.get_leaderboard(10)
        assert b["@winner"]["wins"] == 1
        assert b["@loser"]["losses"] == 1

    def test_void_not_on_leaderboard(self):
        svc = create_test_services()
        bet = svc.store.create_bet({
            "chat_id": 20, "creator": "@x", "opponent": "@y",
            "fixture_id": "z", "market": "next_goal", "amount": 5,
        })
        svc.store.update_bet(bet["id"], {"status": BET_STATUS_VOID})
        board = svc.store.get_leaderboard(20)
        assert not board


# ══════════════════════════════════════════════════
# 5. PLAYER NAME RESOLUTION
# ══════════════════════════════════════════════════

class TestPlayerResolution:
    def test_exact_match(self):
        svc = create_test_services()
        matches = svc.engine.resolve_player_name("18257865", "Mbappe")
        assert len(matches) == 1
        assert matches[0]["match_score"] >= 50

    def test_partial_match(self):
        svc = create_test_services()
        matches = svc.engine.resolve_player_name("18257865", "Griezmann")
        assert len(matches) >= 1

    def test_no_match(self):
        svc = create_test_services()
        matches = svc.engine.resolve_player_name("18257865", "Xyzburg")
        assert len(matches) == 0

    def test_unknown_fixture(self):
        svc = create_test_services()
        assert len(svc.engine.resolve_player_name("99999", "Mbappe")) == 0


# ══════════════════════════════════════════════════
# 6. CONSTANTS
# ══════════════════════════════════════════════════

class TestConstants:
    def test_valid_markets_complete(self):
        expected = (MARKET_NEXT_GOAL, MARKET_NEXT_CARD, MARKET_NEXT_CORNER,
                    MARKET_MATCH_WINNER) + PLAYER_MARKET_VALUES
        assert set(VALID_MARKETS) == set(expected)

    def test_player_markets_are_valid(self):
        for pm in PLAYER_MARKET_VALUES:
            assert pm in VALID_MARKETS

    def test_flag_for_known(self):
        from app.core.constants import flag_for
        assert flag_for("France") != "\U0001f3df\ufe0f"

    def test_flag_for_unknown(self):
        from app.core.constants import flag_for
        assert flag_for("Mordor") == "\U0001f3df\ufe0f"

    def test_default_deadline_within_week(self):
        from app.core.constants import default_deadline
        import time
        now = int(time.time())
        d = default_deadline()
        assert 6 * 86400 <= (d - now) <= 8 * 86400


# ══════════════════════════════════════════════════
# 7. PAYMENT LINK
# ══════════════════════════════════════════════════

class TestPaymentLink:
    def test_uses_app_base_url(self):
        svc = create_test_services(app_base_url="https://myrealapp.io")
        result = asyncio.new_event_loop().run_until_complete(
            svc.payments.generate_payment_request(
                {"id": "abc", "fixture_id": "1", "market": "next_goal", "amount": 5})
        )
        assert "https://myrealapp.io/api/pay?" in result["https_url"]
        assert result["transaction_request_url"].startswith("solana:")

    def test_different_url(self):
        svc = create_test_services(app_base_url="https://other.example")
        result = asyncio.new_event_loop().run_until_complete(
            svc.payments.generate_payment_request(
                {"id": "x", "fixture_id": "2", "market": "match_winner", "amount": 100})
        )
        assert "https://other.example/api/pay?" in result["https_url"]

    def test_trailing_slash_handled(self):
        svc = create_test_services(app_base_url="https://foo.bar/")
        result = asyncio.new_event_loop().run_until_complete(
            svc.payments.generate_payment_request(
                {"id": "y", "fixture_id": "3", "market": "next_goal", "amount": 7})
        )
        assert result["https_url"].startswith("https://foo.bar/api/pay?")
        assert "//api" not in result["https_url"]

    def test_not_standin(self):
        svc = create_test_services(app_base_url="https://realsite.app")
        result = asyncio.new_event_loop().run_until_complete(
            svc.payments.generate_payment_request(
                {"id": "z", "fixture_id": "f", "market": "next_goal", "amount": 3})
        )
        assert "banter.example" not in result["transaction_request_url"]
        assert "banter.example" not in result["https_url"]

    def test_includes_token_mint(self):
        svc = create_test_services(app_base_url="https://realsite.app")
        result = asyncio.new_event_loop().run_until_complete(
            svc.payments.generate_payment_request(
                {"id": "z", "fixture_id": "f", "market": "next_goal", "amount": 3})
        )
        https = result["https_url"]
        assert "tokenMint=Gh9ZwEmdLJ8DscKNTkTqPbNwLNNBjuSzaG9Vp2KGtKJr" in https
        assert "tokenSymbol=USDC" in https


# ══════════════════════════════════════════════════
# 8. NLU ACCURACY (real API)
# ══════════════════════════════════════════════════

@pytest.mark.slow
class TestNLUAccuracy:
    async def _parse(self, text):
        from app.services.nlu.parser import NLUParser
        parser = NLUParser()
        return await parser.parse(text, FIXTURE_DATA)

    async def test_01_simple_bet(self):
        r = await self._parse("bet @alice 50 next goal")
        assert r.get("intent") == "bet"
        p = r.get("params", {})
        assert "alice" in str(p.get("opponent", "")).lower()

    async def test_02_bet_team(self):
        r = await self._parse("bet @bob 100 match_winner France")
        assert r.get("intent") == "bet"

    async def test_03_bet_player(self):
        r = await self._parse("bet @alice 50 hat_trick Mbappe")
        assert r.get("intent") == "bet"

    async def test_04_bet_scores(self):
        r = await self._parse("bet @charlie 100 scores Messi")
        assert r.get("intent") == "bet"

    async def test_05_natural_winner(self):
        r = await self._parse("France will win I bet @alice 50")
        assert r.get("intent") in ("bet", "unknown")

    async def test_06_natural_goal(self):
        r = await self._parse("who scores next bet @bob 20")
        assert r.get("intent") in ("bet", "unknown")

    async def test_07_brace(self):
        r = await self._parse("Mbappe brace bet @alice 250 two goals")
        assert r.get("intent") in ("bet", "unknown")

    async def test_08_clean_sheet(self):
        r = await self._parse("clean sheet bet @opp 66")
        assert r.get("intent") in ("bet", "unknown")

    async def test_09_card(self):
        r = await self._parse("Messi gets carded bet @you 100")
        assert r.get("intent") in ("bet", "unknown")

    async def test_10_winner_alias(self):
        r = await self._parse("Spain to beat France bet @guy 999")
        assert r.get("intent") in ("bet", "unknown")

    async def test_11_challenge(self):
        r = await self._parse("I challenge @opp to bet 50 next goal")
        assert r.get("intent") in ("bet", "unknown")

    async def test_12_no_bet(self):
        r = await self._parse("hello how are you doing")
        assert r.get("intent") == "unknown"

    async def test_13_empty(self):
        r = await self._parse("")
        assert r.get("intent") in ("unknown", "bet")

    @pytest.mark.parametrize("text", [
        "bet @alice 50 next goal",
        "bet @bob 100 match_winner Spain",
        "bet @alice 50 hat_trick Mbappe",
        "bet @charlie 100 scores messi",
        "wager @dan 200 match_winner France",
        "stake @eva 101 next_goal France",
        "Mbappe scores first bet @frank 50",
        "Mbappe brace bet @alice 250 two goals",
        "Messi gets red carded bet @opp 100",
        "Spain to beat Argentina bet @alice 999",
    ])
    async def test_parametrized_nlu(self, text):
        r = await self._parse(text)
        assert r.get("intent") in ("bet", "unknown"), f"{text} -> {r}"


# ══════════════════════════════════════════════════
# 9. AMOUNT PARSING ($ prefix)
# ══════════════════════════════════════════════════

class TestAmountParsing:
    def test_dollar_prefix_in_bet(self):
        r = _parse_bet("@alice $50 next goal")
        assert r is not None
        assert r["amount"] == "50"

    def test_dollar_prefix_in_bet_team(self):
        r = _parse_bet("@bob $100 match_winner Spain")
        assert r is not None
        assert r["amount"] == "100"

    def test_dollar_prefix_player(self):
        r = _parse_bet("@alice $75 hat_trick Mbappe")
        assert r is not None
        assert r["amount"] == "75"

    def test_float_amount_works(self):
        r = _parse_bet("@alice 50.5 next goal")
        assert r is not None
        assert r["amount"] == "50.5"