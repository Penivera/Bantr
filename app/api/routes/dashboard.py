import json
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from app.core.config import settings
from app.core.dependencies import get_container

BASE_DIR = Path(__file__).resolve().parent.parent

templates_dir = str(BASE_DIR / "templates")
jinja_env = Environment(loader=FileSystemLoader(templates_dir))
static_dir = str(BASE_DIR / "static")


def render_template(name: str, **kwargs) -> str:
    template = jinja_env.get_template(name)
    return template.render(**kwargs)


def create_app(lifespan=None) -> FastAPI:
    app = FastAPI(title="BanterBot", version="0.1.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return render_template("index.html", bot_url=f"https://t.me/{settings.telegram_bot_username}")

    @app.post("/webhook")
    async def webhook(request: Request):
        if settings.app_debug:
            return PlainTextResponse("webhook disabled in debug mode")

        try:
            data = await request.json()
            from aiogram.types import Update
            update = Update.model_validate(data)
            container = get_container()
            await container.bot.feed_update(update)
        except Exception:
            pass
        return PlainTextResponse("ok")

    @app.get("/status")
    async def status():
        try:
            container = get_container()
            engine = container.engine
            return JSONResponse({
                "fixture_count": len(engine.fixture_info),
                "tracked_count": len(engine.tracked),
                "active_bets": len(engine.active_bets),
                "fixtures": [
                    {"id": fid, **info}
                    for fid, info in engine.fixture_info.items()
                ],
            })
        except Exception:
            return JSONResponse({"error": "not ready"}, status_code=503)

    return app
