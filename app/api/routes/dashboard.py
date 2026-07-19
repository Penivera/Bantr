import json
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from app.core.config import settings
from app.core.dependencies import get_container
from app.core.logging import get_logger

logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

templates_dir = str(BASE_DIR / "templates")
jinja_env = Environment(loader=FileSystemLoader(templates_dir))
static_dir = str(BASE_DIR / "static")
spa_dir = str(BASE_DIR / "static" / "spa")


def render_template(name: str, **kwargs) -> str:
    template = jinja_env.get_template(name)
    return template.render(**kwargs)


def create_app(lifespan=None) -> FastAPI:
    from fastapi.middleware.cors import CORSMiddleware
    app = FastAPI(title="BanterBot", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    from app.api.routes.pay import router as pay_router
    from app.api.routes.payments import payments_router
    app.include_router(pay_router)
    app.include_router(payments_router)

    @app.get("/")
    async def index(request: Request):
        if Path(spa_dir, "index.html").exists():
            return FileResponse(Path(spa_dir, "index.html"))
        return render_template("index.html", bot_url=f"https://t.me/{settings.telegram_bot_username}")

    @app.get("/pay")
    @app.get("/{path:path}")
    async def spa_fallback(request: Request, path: str = ""):
        if path.startswith("api/") or path.startswith("static/") or path == "webhook":
            raise HTTPException(status_code=404)
        if Path(spa_dir, "index.html").exists():
            return FileResponse(str(Path(spa_dir, "index.html")))
        raise HTTPException(status_code=404, detail="Not found")

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
        except Exception as exc:
            logger.error("webhook_update_failed", error=str(exc))
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
