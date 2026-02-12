"""Pydantic models for request/response validation."""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


# ─── Channel Models ───────────────────────────────────────────────────────────

class ChannelCreate(BaseModel):
    """Request model for adding a new channel."""
    url_or_id: str = Field(..., description="YouTube channel URL, handle, or channel ID")


class ChannelUpdate(BaseModel):
    """Request model for updating a channel."""
    channel_name: Optional[str] = None
    is_active: Optional[bool] = None


class ChannelResponse(BaseModel):
    """Response model for a channel."""
    id: int
    channel_id: str
    channel_name: str
    channel_url: str
    uploads_playlist_id: Optional[str] = None
    is_active: bool
    added_at: str
    last_checked_at: Optional[str] = None
    video_count: int = 0
    code_count: int = 0


# ─── Video Models ─────────────────────────────────────────────────────────────

class VideoResponse(BaseModel):
    """Response model for a video."""
    id: int
    channel_id: int
    channel_name: str = ""
    youtube_video_id: str
    title: str
    video_url: str
    published_at: Optional[str] = None
    discovered_at: str
    status: str
    error_message: Optional[str] = None
    frames_extracted: int = 0
    processing_started_at: Optional[str] = None
    processing_completed_at: Optional[str] = None
    code_count: int = 0


# ─── Code Models ──────────────────────────────────────────────────────────────

class CodeResponse(BaseModel):
    """Response model for an extracted code."""
    id: int
    video_id: int
    video_title: str = ""
    channel_name: str = ""
    code: str
    code_normalized: str
    source_type: str
    frame_timestamp: Optional[float] = None
    confidence: Optional[float] = None
    discovered_at: str
    is_redeemed: bool = False
    redeemed_at: Optional[str] = None


class CodeUpdate(BaseModel):
    """Request model for updating a code."""
    is_redeemed: Optional[bool] = None


# ─── Dashboard Models ─────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    """Dashboard summary statistics."""
    total_channels: int = 0
    active_channels: int = 0
    total_videos: int = 0
    videos_today: int = 0
    total_codes: int = 0
    codes_today: int = 0
    unredeemed_codes: int = 0
    monitoring_mode: str = "rss"  # "api" or "rss"
    poll_interval: int = 120


# ─── WebSocket Event Models ──────────────────────────────────────────────────

class WSEvent(BaseModel):
    """WebSocket event message."""
    event: str
    data: dict = {}
    timestamp: str = ""

    def __init__(self, **kwargs):
        if "timestamp" not in kwargs or not kwargs["timestamp"]:
            kwargs["timestamp"] = datetime.utcnow().isoformat()
        super().__init__(**kwargs)
