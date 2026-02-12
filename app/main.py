"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db, close_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    logger.info("Starting Pokemon TCG Code Monitor...")
    settings.ensure_directories()
    await init_db()

    mode = "YouTube API" if settings.use_youtube_api else "RSS"
    logger.info(f"Monitoring mode: {mode} (poll every {settings.poll_interval}s)")

    # Import and start scheduler after DB is ready
    from app.scheduler import start_scheduler, stop_scheduler
    await start_scheduler()

    yield

    # Shutdown
    logger.info("Shutting down...")
    await stop_scheduler()
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Pokemon TCG Code Monitor",
    description="Monitor YouTube pack openings for Pokemon TCG redemption codes",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files
static_dir = settings.BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Import and include routers
from app.routers import channels, videos, codes, ws  # noqa: E402

app.include_router(channels.router, prefix="/api/channels", tags=["channels"])
app.include_router(videos.router, prefix="/api/videos", tags=["videos"])
app.include_router(codes.router, prefix="/api/codes", tags=["codes"])
app.include_router(ws.router, tags=["websocket"])


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "monitoring_mode": "api" if settings.use_youtube_api else "rss",
        "poll_interval": settings.poll_interval,
        "cookies_configured": bool(settings.YTDLP_COOKIES_FILE or settings.YTDLP_COOKIES_FROM_BROWSER),
    }


@app.post("/api/settings/cookies")
async def upload_cookies(file: UploadFile):
    """Upload a cookies.txt file for YouTube authentication."""
    cookies_path = settings.DATA_DIR / "cookies.txt"
    content = await file.read()
    cookies_path.write_bytes(content)
    settings.YTDLP_COOKIES_FILE = str(cookies_path)
    logger.info(f"Cookies file uploaded: {cookies_path}")
    return {"status": "ok", "message": "Cookies uploaded successfully"}


@app.get("/api/stats")
async def get_stats():
    """Dashboard statistics."""
    from app.database import get_db

    db = await get_db()

    stats = {}

    row = await db.execute("SELECT COUNT(*) as c FROM channels")
    stats["total_channels"] = (await row.fetchone())[0]

    row = await db.execute("SELECT COUNT(*) as c FROM channels WHERE is_active = 1")
    stats["active_channels"] = (await row.fetchone())[0]

    row = await db.execute("SELECT COUNT(*) as c FROM videos")
    stats["total_videos"] = (await row.fetchone())[0]

    row = await db.execute(
        "SELECT COUNT(*) as c FROM videos WHERE date(discovered_at) = date('now')"
    )
    stats["videos_today"] = (await row.fetchone())[0]

    row = await db.execute("SELECT COUNT(*) as c FROM codes")
    stats["total_codes"] = (await row.fetchone())[0]

    row = await db.execute(
        "SELECT COUNT(*) as c FROM codes WHERE date(discovered_at) = date('now')"
    )
    stats["codes_today"] = (await row.fetchone())[0]

    row = await db.execute("SELECT COUNT(*) as c FROM codes WHERE is_redeemed = 0")
    stats["unredeemed_codes"] = (await row.fetchone())[0]

    stats["monitoring_mode"] = "api" if settings.use_youtube_api else "rss"
    stats["poll_interval"] = settings.poll_interval

    return stats


# Serve index.html at root
@app.get("/")
async def root():
    """Serve the main page."""
    from fastapi.responses import FileResponse

    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Pokemon TCG Code Monitor API", "docs": "/docs"}
