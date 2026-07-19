from dataclasses import dataclass, field
from typing import Any, Callable
from app.services.txline.auth import TxLineCredentials, bootstrap_credentials
from app.services.txline.stream import TxLineStreamClient
from app.services.telegram.bot import TelegramBot
from app.services.payments.solana_pay import SolanaPayService
from app.services.nlu.parser import NLUParser
from app.services.betting.engine import BetEngine, BetStore
from app.services.state.redis_store import RedisStore


@dataclass
class AppContainer:
    credentials: TxLineCredentials | None = None
    stream: TxLineStreamClient | None = None
    bot: TelegramBot | None = None
    payments: SolanaPayService | None = None
    nlu: NLUParser | None = None
    engine: BetEngine | None = None
    store: BetStore = field(default_factory=BetStore)
    redis: RedisStore | None = None

    async def initialize(self) -> None:
        from app.core.security import WALLET, WALLET_PUBKEY
        from app.db.session import init_db
        self.redis = RedisStore()
        await self.redis.connect()
        self.store.redis = self.redis

        try:
            await init_db()
            await self.store.load_from_db()
        except Exception:
            import logging
            logging.getLogger(__name__).warning("db_init_failed — running without database")

        self.credentials = await bootstrap_credentials(WALLET)
        self.stream = TxLineStreamClient(self.credentials)
        self.bot = TelegramBot(self)
        self.payments = SolanaPayService()
        self.nlu = NLUParser()
        self.engine = BetEngine(self.store, self.stream, self.bot, self.payments, self.nlu, redis_store=self.redis)


_container: AppContainer | None = None


def get_container() -> AppContainer:
    global _container
    if _container is None:
        _container = AppContainer()
    return _container
