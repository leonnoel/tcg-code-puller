"""SQLite database setup and access."""

import aiosqlite
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level connection reference
_db: aiosqlite.Connection | None = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT UNIQUE NOT NULL,
    channel_name TEXT NOT NULL,
    channel_url TEXT NOT NULL,
    uploads_playlist_id TEXT,
    is_active BOOLEAN DEFAULT 1,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER REFERENCES channels(id),
    youtube_video_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    video_url TEXT NOT NULL,
    published_at TIMESTAMP,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    frames_extracted INTEGER DEFAULT 0,
    processing_started_at TIMESTAMP,
    processing_completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER REFERENCES videos(id),
    code TEXT NOT NULL,
    code_normalized TEXT NOT NULL,
    source_type TEXT NOT NULL,
    frame_timestamp REAL,
    frame_path TEXT,
    confidence REAL,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_redeemed BOOLEAN DEFAULT 0,
    redeemed_at TIMESTAMP,
    UNIQUE(code_normalized, video_id)
);

CREATE TABLE IF NOT EXISTS scan_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER REFERENCES videos(id),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    frames_scanned INTEGER DEFAULT 0,
    qr_codes_found INTEGER DEFAULT 0,
    ocr_codes_found INTEGER DEFAULT 0,
    total_unique_codes INTEGER DEFAULT 0,
    error_message TEXT
);
"""


async def get_db() -> aiosqlite.Connection:
    """Get the database connection, creating it if needed."""
    global _db
    if _db is None:
        await init_db()
    return _db


async def init_db() -> None:
    """Initialize database connection and create tables."""
    global _db
    settings.ensure_directories()

    logger.info(f"Initializing database at {settings.DB_PATH}")
    _db = await aiosqlite.connect(str(settings.DB_PATH))
    _db.row_factory = aiosqlite.Row

    # Enable WAL mode for better concurrent read/write performance
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")

    # Create tables
    await _db.executescript(SCHEMA_SQL)
    await _db.commit()
    logger.info("Database initialized successfully")


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
        logger.info("Database connection closed")
