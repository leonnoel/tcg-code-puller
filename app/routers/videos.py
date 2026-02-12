"""Video management API endpoints."""

import re
import logging
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Query

from app.database import get_db
from app.models import VideoResponse

logger = logging.getLogger(__name__)
router = APIRouter()


class ManualVideoRequest(BaseModel):
    url: str


@router.post("/add")
async def add_video_manually(req: ManualVideoRequest):
    """Add a video by URL for processing (even if not from a monitored channel).

    Useful for quickly processing a specific video you found.
    """
    url = req.url.strip()

    # Extract YouTube video ID from URL
    match = re.search(r'(?:v=|youtu\.be/|shorts/)([\w-]{11})', url)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid YouTube video URL")

    video_id = match.group(1)
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    db = await get_db()

    # Check if already exists
    cursor = await db.execute(
        "SELECT id, status FROM videos WHERE youtube_video_id = ?", (video_id,)
    )
    existing = await cursor.fetchone()
    if existing:
        existing = dict(existing)
        if existing["status"] in ("completed", "processing", "downloading"):
            raise HTTPException(
                status_code=409,
                detail=f"Video already exists (status: {existing['status']})"
            )
        # Reset to pending if failed/skipped
        await db.execute(
            "UPDATE videos SET status = 'pending', error_message = NULL WHERE id = ?",
            (existing["id"],),
        )
        await db.commit()
        return {"status": "ok", "message": "Video re-queued for processing", "video_id": existing["id"]}

    # Get or create a placeholder channel for manual videos
    cursor = await db.execute("SELECT id FROM channels WHERE channel_id = 'manual'")
    channel_row = await cursor.fetchone()
    if not channel_row:
        await db.execute(
            """INSERT INTO channels (channel_id, channel_name, channel_url, is_active)
               VALUES ('manual', 'Manual Additions', 'https://youtube.com', 0)"""
        )
        await db.commit()
        cursor = await db.execute("SELECT id FROM channels WHERE channel_id = 'manual'")
        channel_row = await cursor.fetchone()

    channel_db_id = channel_row[0]

    # Try to get video title
    title = f"Manual: {video_id}"
    try:
        import httpx
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(video_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }, timeout=10)
            title_match = re.search(r'<title>([^<]+?)(?:\s*-\s*YouTube)?</title>', resp.text)
            if title_match:
                fetched = title_match.group(1).strip()
                if fetched and fetched.lower() != "youtube":
                    title = fetched
    except Exception:
        pass

    await db.execute(
        """INSERT INTO videos (channel_id, youtube_video_id, title, video_url)
           VALUES (?, ?, ?, ?)""",
        (channel_db_id, video_id, title, video_url),
    )
    await db.commit()

    cursor = await db.execute("SELECT id FROM videos WHERE youtube_video_id = ?", (video_id,))
    new_row = await cursor.fetchone()

    logger.info(f"Manual video added: {title} ({video_id})")
    return {"status": "ok", "message": f"Video '{title}' queued for processing", "video_id": new_row[0]}


@router.get("", response_model=list[VideoResponse])
async def list_videos(
    channel_id: int | None = Query(None, description="Filter by channel"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List processed videos."""
    db = await get_db()

    query = """
        SELECT v.*, c.channel_name,
               COALESCE(cd.code_count, 0) as code_count
        FROM videos v
        JOIN channels c ON v.channel_id = c.id
        LEFT JOIN (
            SELECT video_id, COUNT(*) as code_count FROM codes GROUP BY video_id
        ) cd ON cd.video_id = v.id
    """
    conditions = []
    params = []

    if channel_id is not None:
        conditions.append("v.channel_id = ?")
        params.append(channel_id)
    if status is not None:
        conditions.append("v.status = ?")
        params.append(status)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY v.discovered_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


# Static routes MUST be defined before parameterized routes
@router.post("/bulk/skip")
async def bulk_skip_videos(video_ids: list[int]):
    """Skip multiple videos at once."""
    db = await get_db()
    for vid in video_ids:
        await db.execute(
            "UPDATE videos SET status = 'skipped' WHERE id = ? AND status = 'pending'",
            (vid,),
        )
    await db.commit()
    return {"status": "ok", "skipped": len(video_ids)}


@router.post("/{video_id}/reprocess")
async def reprocess_video(video_id: int):
    """Queue a video for reprocessing."""
    db = await get_db()

    cursor = await db.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")

    # Reset status to pending
    await db.execute(
        "UPDATE videos SET status = 'pending', error_message = NULL WHERE id = ?",
        (video_id,),
    )
    await db.commit()

    return {"status": "ok", "message": "Video queued for reprocessing"}


@router.post("/{video_id}/skip")
async def skip_video(video_id: int):
    """Skip processing for a video."""
    db = await get_db()

    cursor = await db.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")

    await db.execute(
        "UPDATE videos SET status = 'skipped' WHERE id = ?",
        (video_id,),
    )
    await db.commit()

    return {"status": "ok", "message": "Video skipped"}


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(video_id: int):
    """Get details for a specific video."""
    db = await get_db()
    cursor = await db.execute("""
        SELECT v.*, c.channel_name,
               COALESCE(cd.code_count, 0) as code_count
        FROM videos v
        JOIN channels c ON v.channel_id = c.id
        LEFT JOIN (
            SELECT video_id, COUNT(*) as code_count FROM codes GROUP BY video_id
        ) cd ON cd.video_id = v.id
        WHERE v.id = ?
    """, (video_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")
    return dict(row)
