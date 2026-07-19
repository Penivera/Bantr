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

    # ── bets (persistent index) ──

    async def save_bet(self, bet: dict) -> None:
        import json
        bet_id = bet["id"]
        serializable = {k: v for k, v in bet.items() if v is not None}
        await self.client.hset(self._k("bet", bet_id), mapping={
            k: json.dumps(v) if not isinstance(v, (str, int, float, bool)) else v
            for k, v in serializable.items()
        })
        creator = bet.get("creator")
        opponent = bet.get("opponent")
        chat_id = bet.get("chat_id")
        status = bet.get("status", "open")
        if creator:
            await self.client.sadd(self._k("bet", "by_creator", creator), bet_id)
        if opponent:
            await self.client.sadd(self._k("bet", "by_opponent", opponent), bet_id)
        if chat_id is not None:
            await self.client.sadd(self._k("bet", "by_chat", str(chat_id)), bet_id)
        await self.client.sadd(self._k("bet", "by_status", status), bet_id)

    async def update_bet_status(self, bet_id: str, status: str, extra: dict | None = None) -> None:
        import json
        bet = await self.get_bet(bet_id)
        if not bet:
            return
        old_status = bet.get("status", "open")
        if old_status != status:
            await self.client.srem(self._k("bet", "by_status", old_status), bet_id)
            await self.client.sadd(self._k("bet", "by_status", status), bet_id)
        patch = {"status": status}
        if extra:
            patch.update(extra)
        for k, v in patch.items():
            val = json.dumps(v) if not isinstance(v, (str, int, float, bool)) else str(v)
            await self.client.hset(self._k("bet", bet_id), k, val)

    async def get_bet(self, bet_id: str) -> dict | None:
        import json
        raw = await self.client.hgetall(self._k("bet", bet_id))
        if not raw:
            return None
        bet = {}
        for k, v in raw.items():
            try:
                bet[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                bet[k] = v
        bet["id"] = bet_id
        return bet

    async def get_bets_for_user(self, username: str) -> list[dict]:
        creator_ids = await self.client.smembers(self._k("bet", "by_creator", username))
        opponent_ids = await self.client.smembers(self._k("bet", "by_opponent", username))
        all_ids = set(creator_ids) | set(opponent_ids)
        bets = []
        for bid in all_ids:
            bet = await self.get_bet(bid)
            if bet:
                bets.append(bet)
        return sorted(bets, key=lambda b: b.get("created_at", ""), reverse=True)

    async def get_bets_for_chat(self, chat_id: int, status: str | None = None) -> list[dict]:
        chat_ids = await self.client.smembers(self._k("bet", "by_chat", str(chat_id)))
        if status:
            status_ids = await self.client.smembers(self._k("bet", "by_status", status))
            chat_ids = chat_ids & status_ids
        bets = []
        for bid in chat_ids:
            bet = await self.get_bet(bid)
            if bet:
                bets.append(bet)
        return sorted(bets, key=lambda b: b.get("created_at", ""), reverse=True)

    async def get_challenges_for_user(self, username: str) -> list[dict]:
        opponent_ids = await self.client.smembers(self._k("bet", "by_opponent", username))
        bets = []
        for bid in opponent_ids:
            bet = await self.get_bet(bid)
            if bet and bet.get("status") == "open":
                bets.append(bet)
        return sorted(bets, key=lambda b: b.get("created_at", ""), reverse=True)

    async def get_pending_count(self, username: str) -> int:
        opponent_ids = await self.client.smembers(self._k("bet", "by_opponent", username))
        count = 0
        for bid in opponent_ids:
            raw = await self.client.hget(self._k("bet", bid), "status")
            if raw and '"open"' in raw:
                count += 1
        return count
