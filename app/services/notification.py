"""Notification service — WebSocket broadcast + optional webhook."""

import logging
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def notify_code_found(code: str, video_title: str, source: str, channel_name: str = ""):
    """Send notifications when a new code is found."""
    from app.routers.ws import broadcast

    # Always broadcast via WebSocket
    await broadcast("code_found", {
        "code": code,
        "source": source,
        "video_title": video_title,
        "channel_name": channel_name,
    })

    logger.info(f"🎉 New code found: {code} from '{video_title}' via {source}")
