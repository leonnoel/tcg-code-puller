"""Video management API endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Query

from app.database import get_db
from app.models import VideoResponse

logger = logging.getLogger(__name__)
router = APIRouter()


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
