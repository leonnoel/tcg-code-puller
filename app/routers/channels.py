"""Channel management API endpoints."""

import logging
from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.models import ChannelCreate, ChannelUpdate, ChannelResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=list[ChannelResponse])
async def list_channels():
    """List all monitored channels."""
    db = await get_db()
    cursor = await db.execute("""
        SELECT c.*,
               COALESCE(v.video_count, 0) as video_count,
               COALESCE(cd.code_count, 0) as code_count
        FROM channels c
        LEFT JOIN (
            SELECT channel_id, COUNT(*) as video_count FROM videos GROUP BY channel_id
        ) v ON v.channel_id = c.id
        LEFT JOIN (
            SELECT v2.channel_id, COUNT(*) as code_count
            FROM codes co JOIN videos v2 ON co.video_id = v2.id
            GROUP BY v2.channel_id
        ) cd ON cd.channel_id = c.id
        ORDER BY c.added_at DESC
    """)
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.post("", response_model=ChannelResponse, status_code=201)
async def add_channel(channel: ChannelCreate):
    """Add a new YouTube channel to monitor."""
    from app.services.youtube_monitor import resolve_channel

    try:
        info = await resolve_channel(channel.url_or_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not resolve channel: {e}")

    db = await get_db()

    # Check if already exists
    cursor = await db.execute(
        "SELECT id FROM channels WHERE channel_id = ?", (info["channel_id"],)
    )
    if await cursor.fetchone():
        raise HTTPException(status_code=409, detail="Channel already being monitored")

    await db.execute(
        """INSERT INTO channels (channel_id, channel_name, channel_url, uploads_playlist_id)
           VALUES (?, ?, ?, ?)""",
        (info["channel_id"], info["channel_name"], info["channel_url"], info.get("uploads_playlist_id")),
    )
    await db.commit()

    # Return the newly created channel
    cursor = await db.execute(
        "SELECT *, 0 as video_count, 0 as code_count FROM channels WHERE channel_id = ?",
        (info["channel_id"],),
    )
    row = await cursor.fetchone()
    return dict(row)


@router.put("/{channel_id}")
async def update_channel(channel_id: int, update: ChannelUpdate):
    """Update a channel's settings."""
    db = await get_db()

    cursor = await db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Channel not found")

    updates = []
    values = []
    if update.channel_name is not None:
        updates.append("channel_name = ?")
        values.append(update.channel_name)
    if update.is_active is not None:
        updates.append("is_active = ?")
        values.append(update.is_active)

    if updates:
        values.append(channel_id)
        await db.execute(
            f"UPDATE channels SET {', '.join(updates)} WHERE id = ?", values
        )
        await db.commit()

    return {"status": "ok"}


@router.delete("/{channel_id}")
async def delete_channel(channel_id: int):
    """Remove a channel from monitoring."""
    db = await get_db()

    cursor = await db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Channel not found")

    # Delete associated data
    await db.execute("""
        DELETE FROM codes WHERE video_id IN (SELECT id FROM videos WHERE channel_id = ?)
    """, (channel_id,))
    await db.execute("""
        DELETE FROM scan_logs WHERE video_id IN (SELECT id FROM videos WHERE channel_id = ?)
    """, (channel_id,))
    await db.execute("DELETE FROM videos WHERE channel_id = ?", (channel_id,))
    await db.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
    await db.commit()

    return {"status": "ok"}


@router.post("/{channel_id}/check")
async def check_channel_now(channel_id: int):
    """Manually trigger a check for new videos on this channel."""
    db = await get_db()

    cursor = await db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Channel not found")

    from app.services.youtube_monitor import check_channel_for_new_videos

    new_videos = await check_channel_for_new_videos(dict(row))
    return {"status": "ok", "new_videos": len(new_videos)}
