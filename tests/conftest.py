import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass
from typing import Any

from app.services.betting.engine import BetStore, BetEngine
from app.services.payments.solana_pay import SolanaPayService
from app.services.nlu.parser import NLUParser


FIXTURE_DATA = [
    {"id": "18257865", "home": "France", "away": "Spain", "stage": "Semi-Final", "time_utc": "2026-07-19T20:00:00Z"},
    {"id": "18257739", "home": "Argentina", "away": "Brazil", "stage": "Semi-Final", "time_utc": "2026-07-18T20:00:00Z"},
]

ALL_PLAYERS = [
    {"preferred_name": "Mbappe, Kylian", "normative_id": 1, "team_name": "France", "match_score": 100, "match_display": "Mbappe, Kylian"},
    {"preferred_name": "Griezmann, Antoine", "normative_id": 10, "team_name": "France", "match_score": 100, "match_display": "Griezmann, Antoine"},
    {"preferred_name": "Messi, Lionel", "normative_id": 2, "team_name": "Argentina", "match_score": 100, "match_display": "Messi, Lionel"},
    {"preferred_name": "Neymar, Jr", "normative_id": 3, "team_name": "Brazil", "match_score": 100, "match_display": "Neymar, Jr"},
]


class MessageCollector:
    def __init__(self):
        self.messages: list[dict] = []

    def send(self, chat_id: int, text: str, **kwargs):
        self.messages.append({"chat_id": chat_id, "text": text, **kwargs})

    def last_text(self) -> str | None:
        return self.messages[-1]["text"] if self.messages else None

    def text_contains(self, substring: str) -> bool:
        return any(substring in m["text"] for m in self.messages)

    def clear(self):
        self.messages.clear()


class MockBot:
    def __init__(self, collector: MessageCollector):
        self.collector = collector

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self.collector.send(chat_id, text, **kwargs)
        return MagicMock(message_id=1)


class MockStream:
    def __init__(self):
        self.callbacks: dict[str, list] = {}

    def on_match_event(self, fixture_id: str, callback):
        self.callbacks.setdefault(fixture_id, []).append(callback)

    async def start(self):
        pass

    async def stop(self):
        pass


@dataclass
class TestServices:
    store: BetStore
    engine: BetEngine
    payments: Any
    nlu: Any
    collector: MessageCollector
    mock_bot: MockBot
    mock_stream: MockStream


def create_test_services(app_base_url: str = "https://banter.example") -> TestServices:
    from app.core.config import settings

    collector = MessageCollector()
    mock_bot = MockBot(collector)
    mock_stream = MockStream()

    store = BetStore()
    engine = BetEngine(store, mock_stream, mock_bot, None, None, redis_store=None)
    for f in FIXTURE_DATA:
        engine.fixture_info[f["id"]] = f

    engine.player_rosters["18257865"] = {
        1: {"preferred_name": "Mbappe, Kylian", "normative_id": 1, "team_name": "France"},
        10: {"preferred_name": "Griezmann, Antoine", "normative_id": 10, "team_name": "France"},
    }
    engine.all_players_by_fixture["18257865"] = list(engine.player_rosters["18257865"].values())
    engine.player_rosters["18257739"] = {
        2: {"preferred_name": "Messi, Lionel", "normative_id": 2, "team_name": "Argentina"},
    }
    engine.all_players_by_fixture["18257739"] = list(engine.player_rosters["18257739"].values())

    settings.app_base_url = app_base_url

    payments = SolanaPayService()

    nlu = MagicMock(spec=NLUParser)
    nlu.parse = AsyncMock(return_value={"intent": "unknown", "params": {}, "confidence": 0})
    nlu.resolve_player_team = AsyncMock(return_value=None)

    return TestServices(
        store=store, engine=engine, payments=payments, nlu=nlu,
        collector=collector, mock_bot=mock_bot, mock_stream=mock_stream,
    )


@pytest.fixture
def svc():
    return create_test_services()
