"""Background scheduler for polling and processing."""

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings

logger = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None
_processing_lock = asyncio.Lock()


async def poll_channels():
    """Check all active channels for new videos."""
    from app.database import get_db
    from app.services.youtube_monitor import check_channel_for_new_videos

    try:
        db = await get_db()
        cursor = await db.execute("SELECT * FROM channels WHERE is_active = 1")
        channels = [dict(row) for row in await cursor.fetchall()]

        if not channels:
            return

        total_new = 0
        for channel in channels:
            try:
                new_videos = await check_channel_for_new_videos(channel)
                total_new += len(new_videos)

                # Update last_checked_at
                await db.execute(
                    "UPDATE channels SET last_checked_at = ? WHERE id = ?",
                    (datetime.utcnow().isoformat(), channel["id"]),
                )
                await db.commit()
            except Exception as e:
                logger.error(f"Error checking channel {channel['channel_name']}: {e}")

        if total_new > 0:
            logger.info(f"Found {total_new} new video(s) across {len(channels)} channel(s)")

    except Exception as e:
        logger.error(f"Error in poll_channels: {e}")


async def process_pending_videos():
    """Process any pending videos."""
    if _processing_lock.locked():
        return  # Already processing

    async with _processing_lock:
        from app.database import get_db
        from app.services.video_processor import process_video

        try:
            db = await get_db()
            cursor = await db.execute(
                "SELECT * FROM videos WHERE status = 'pending' ORDER BY discovered_at DESC LIMIT 1"
            )
            video = await cursor.fetchone()

            if video:
                video = dict(video)
                logger.info(f"Processing video: {video['title']}")
                await process_video(video)

        except Exception as e:
            logger.error(f"Error in process_pending_videos: {e}")


async def cleanup_old_files():
    """Remove old downloaded videos and frames."""
    import os
    import time

    try:
        video_cutoff = time.time() - (settings.VIDEO_RETENTION_HOURS * 3600)
        frame_cutoff = time.time() - (settings.FRAME_RETENTION_HOURS * 3600)

        # Clean old videos
        if settings.VIDEOS_DIR.exists():
            for f in settings.VIDEOS_DIR.iterdir():
                if f.is_file() and f.stat().st_mtime < video_cutoff:
                    f.unlink()
                    logger.debug(f"Cleaned up video: {f.name}")

        # Clean old frames (only those not associated with codes)
        # Frames are stored in FRAMES_DIR/<video_id>/frame_*.jpg
        if settings.FRAMES_DIR.exists():
            from app.database import get_db
            db = await get_db()
            cursor = await db.execute("SELECT DISTINCT frame_path FROM codes WHERE frame_path IS NOT NULL")
            keep_frames = {row[0] for row in await cursor.fetchall()}

            for video_dir in settings.FRAMES_DIR.iterdir():
                if not video_dir.is_dir():
                    continue
                # Check if any file in the directory is old enough to clean
                all_old = True
                for f in video_dir.iterdir():
                    if f.is_file():
                        if str(f) in keep_frames or f.stat().st_mtime >= frame_cutoff:
                            all_old = False
                            break
                # Only remove the whole directory if all frames are old and none are kept
                if all_old and any(video_dir.iterdir()):
                    import shutil
                    shutil.rmtree(str(video_dir), ignore_errors=True)
                    logger.debug(f"Cleaned up frame directory: {video_dir.name}")

    except Exception as e:
        logger.error(f"Error in cleanup_old_files: {e}")


async def start_scheduler():
    """Start the background scheduler."""
    global scheduler
    scheduler = AsyncIOScheduler()

    # Poll channels for new videos
    poll_interval = settings.poll_interval
    scheduler.add_job(
        poll_channels,
        IntervalTrigger(seconds=poll_interval),
        id="poll_channels",
        name=f"Poll channels (every {poll_interval}s)",
        max_instances=1,
    )

    # Process pending videos (check every 10 seconds)
    scheduler.add_job(
        process_pending_videos,
        IntervalTrigger(seconds=10),
        id="process_videos",
        name="Process pending videos",
        max_instances=1,
    )

    # Cleanup old files (every hour)
    scheduler.add_job(
        cleanup_old_files,
        IntervalTrigger(hours=1),
        id="cleanup_files",
        name="Cleanup old files",
        max_instances=1,
    )

    scheduler.start()
    logger.info(f"Scheduler started with {poll_interval}s poll interval")

    # Run an initial poll shortly after startup
    await asyncio.sleep(2)
    asyncio.create_task(poll_channels())


async def stop_scheduler():
    """Stop the background scheduler."""
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info("Scheduler stopped")
