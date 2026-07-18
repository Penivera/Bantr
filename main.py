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
    logger.info("validating_fixtures")
    for f in (
        {"id": "18257865", "home": "France", "away": "England", "time_utc": "2026-07-18T21:00:00Z", "stage": "3rd Place Final"},
        {"id": "18257739", "home": "Spain", "away": "Argentina", "time_utc": "2026-07-19T19:00:00Z", "stage": "Final"},
    ):
        info = await engine.validate_fixture(f["id"])
        if info:
            engine.fixture_info[f["id"]] = info
            engine._ensure_tracked(f["id"])
    logger.info("fixtures_validated", count=len(engine.fixture_info))

    asyncio.create_task(container.stream.start())
    asyncio.create_task(container.bot.start_async())
    logger.info("web_dashboard", url=f"http://localhost:{settings.app_web_port}")
    yield
    logger.info("banterbot_shutting_down")
    os._exit(0)


app = create_app(lifespan=lifespan)


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=settings.app_web_port, log_level="info")


if __name__ == "__main__":
    main()
