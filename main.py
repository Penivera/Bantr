import asyncio
import os
import signal
from contextlib import asynccontextmanager
import uvicorn
from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.dependencies import get_container
from app.api.routes.dashboard import create_app

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app):
    logger.info("banterbot_starting", env="devnet")
    container = get_container()
    await container.initialize()

    engine = container.engine
    await engine.restore_from_redis()

    logger.info("fetching_fixtures")
    from app.services.txline.fixtures import fetch_fixtures
    api_fixtures = await fetch_fixtures(container.credentials)
    allowed_ids = [x.strip() for x in settings.app_fixture_ids.split(",") if x.strip()] if settings.app_fixture_ids else []
    for f in api_fixtures:
        if allowed_ids and f["id"] not in allowed_ids:
            continue
        engine.fixture_info[f["id"]] = f
        engine._ensure_tracked(f["id"])
    logger.info("fixtures_loaded", count=len(engine.fixture_info))

    asyncio.create_task(container.stream.start())
    asyncio.create_task(container.bot.start_async())
    logger.info("web_dashboard", url=f"http://localhost:{settings.app_web_port}")
    yield
    logger.info("banterbot_shutting_down")
    await container.bot.stop_async()
    if container.redis:
        await container.redis.disconnect()


app = create_app(lifespan=lifespan)


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=settings.app_web_port, log_level="info")


if __name__ == "__main__":
    main()
