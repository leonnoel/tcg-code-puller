"""Code management API endpoints."""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.database import get_db
from app.models import CodeResponse, CodeUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=list[CodeResponse])
async def list_codes(
    video_id: int | None = Query(None, description="Filter by video"),
    redeemed: bool | None = Query(None, description="Filter by redeemed status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List extracted codes."""
    db = await get_db()

    query = """
        SELECT co.*, v.title as video_title, c.channel_name
        FROM codes co
        JOIN videos v ON co.video_id = v.id
        JOIN channels c ON v.channel_id = c.id
    """
    conditions = []
    params = []

    if video_id is not None:
        conditions.append("co.video_id = ?")
        params.append(video_id)
    if redeemed is not None:
        conditions.append("co.is_redeemed = ?")
        params.append(redeemed)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY co.discovered_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


# Static routes MUST be before parameterized routes
@router.put("/bulk/redeem")
async def bulk_mark_redeemed(code_ids: list[int]):
    """Mark multiple codes as redeemed."""
    db = await get_db()
    now = datetime.utcnow().isoformat()

    for cid in code_ids:
        await db.execute(
            "UPDATE codes SET is_redeemed = 1, redeemed_at = ? WHERE id = ?",
            (now, cid),
        )
    await db.commit()

    return {"status": "ok", "updated": len(code_ids)}


@router.put("/{code_id}")
async def update_code(code_id: int, update: CodeUpdate):
    """Update a code (e.g., mark as redeemed)."""
    db = await get_db()

    cursor = await db.execute("SELECT * FROM codes WHERE id = ?", (code_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Code not found")

    if update.is_redeemed is not None:
        redeemed_at = datetime.utcnow().isoformat() if update.is_redeemed else None
        await db.execute(
            "UPDATE codes SET is_redeemed = ?, redeemed_at = ? WHERE id = ?",
            (update.is_redeemed, redeemed_at, code_id),
        )
        await db.commit()

    return {"status": "ok"}
