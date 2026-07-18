import redis.asyncio as redis
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

BANTER_PREFIX = "banter"


class RedisStore:
    def __init__(self, redis_url: str | None = None):
        self._url = redis_url or settings.app_redis_url
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        self._client = redis.from_url(self._url, decode_responses=True)
        await self._client.ping()
        logger.info("redis_connected", url=self._url)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("RedisStore not connected — call connect() first")
        return self._client

    def _k(self, *parts: str) -> str:
        return f"{BANTER_PREFIX}:{':'.join(parts)}"

    # ── chat_fixtures ──

    async def set_chat_fixture(self, chat_id: int, fixture_id: str) -> None:
        await self.client.hset(self._k("chat_fixtures"), str(chat_id), fixture_id)

    async def get_chat_fixture(self, chat_id: int) -> str | None:
        return await self.client.hget(self._k("chat_fixtures"), str(chat_id))

    async def get_all_chat_fixtures(self) -> dict[int, str]:
        raw = await self.client.hgetall(self._k("chat_fixtures"))
        return {int(k): v for k, v in raw.items()}

    async def remove_chat_fixture(self, chat_id: int) -> None:
        await self.client.hdel(self._k("chat_fixtures"), str(chat_id))

    # ── verbosity ──

    async def set_verbosity(self, chat_id: int, level: str) -> None:
        await self.client.hset(self._k("verbosity"), str(chat_id), level)

    async def get_verbosity(self, chat_id: int) -> str | None:
        return await self.client.hget(self._k("verbosity"), str(chat_id))

    async def get_all_verbosities(self) -> dict[int, str]:
        raw = await self.client.hgetall(self._k("verbosity"))
        return {int(k): v for k, v in raw.items()}

    # ── last_seq (event deduplication) ──

    async def set_last_seq(self, fixture_id: str, seq: int) -> None:
        await self.client.hset(self._k("last_seq"), fixture_id, seq)

    async def get_last_seq(self, fixture_id: str) -> int | None:
        val = await self.client.hget(self._k("last_seq"), fixture_id)
        return int(val) if val is not None else None

    # ── tracked fixtures (which fixture_ids have been subscribed) ──

    async def add_tracked(self, fixture_id: str) -> None:
        await self.client.sadd(self._k("tracked"), fixture_id)

    async def is_tracked(self, fixture_id: str) -> bool:
        return await self.client.sismember(self._k("tracked"), fixture_id)

    async def get_all_tracked(self) -> set[str]:
        return await self.client.smembers(self._k("tracked"))
