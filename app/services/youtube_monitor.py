"""YouTube channel monitoring — API polling (primary) + RSS fallback."""

import re
import logging
from datetime import datetime

import httpx
import feedparser

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Channel Resolution ──────────────────────────────────────────────────────

# Patterns for extracting channel info from YouTube URLs
CHANNEL_ID_PATTERN = re.compile(r"UC[\w-]{22}")
CHANNEL_URL_PATTERNS = [
    re.compile(r"youtube\.com/channel/(UC[\w-]{22})"),
    re.compile(r"youtube\.com/@([\w.-]+)"),
    re.compile(r"youtube\.com/c/([\w.-]+)"),
    re.compile(r"youtube\.com/user/([\w.-]+)"),
]


async def resolve_channel(url_or_id: str) -> dict:
    """Resolve a YouTube URL, handle, or channel ID to channel info.

    Returns dict with: channel_id, channel_name, channel_url, uploads_playlist_id
    """
    url_or_id = url_or_id.strip()

    # Direct channel ID
    if CHANNEL_ID_PATTERN.fullmatch(url_or_id):
        channel_id = url_or_id
        return await _fetch_channel_info(channel_id)

    # Try to extract from URL patterns
    for pattern in CHANNEL_URL_PATTERNS:
        match = pattern.search(url_or_id)
        if match:
            identifier = match.group(1)
            if identifier.startswith("UC") and len(identifier) == 24:
                return await _fetch_channel_info(identifier)
            else:
                # It's a handle or custom URL — need to resolve to channel ID
                return await _resolve_handle(identifier, url_or_id)

    # Maybe it's just a handle without URL
    if url_or_id.startswith("@"):
        return await _resolve_handle(url_or_id[1:], f"https://www.youtube.com/{url_or_id}")

    # Try treating it as a channel ID anyway
    if len(url_or_id) == 24 and url_or_id.startswith("UC"):
        return await _fetch_channel_info(url_or_id)

    # Try as a handle
    return await _resolve_handle(url_or_id, f"https://www.youtube.com/@{url_or_id}")


async def _resolve_handle(handle: str, url: str) -> dict:
    """Resolve a YouTube handle to a channel ID by scraping the page."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            if not url.startswith("http"):
                url = f"https://www.youtube.com/@{handle}"

            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }, timeout=15)
            resp.raise_for_status()

            # Extract channel ID from page source
            text = resp.text

            # Try multiple patterns
            for pattern in [
                r'"externalId"\s*:\s*"(UC[\w-]{22})"',
                r'"channelId"\s*:\s*"(UC[\w-]{22})"',
                r'data-channel-external-id="(UC[\w-]{22})"',
                r'"browse_id"\s*:\s*"(UC[\w-]{22})"',
            ]:
                match = re.search(pattern, text)
                if match:
                    channel_id = match.group(1)
                    # Try to get channel name
                    name_match = re.search(r'"channelName"\s*:\s*"([^"]+)"', text)
                    if not name_match:
                        name_match = re.search(r'"author"\s*:\s*"([^"]+)"', text)
                    if not name_match:
                        name_match = re.search(r'"name"\s*:\s*"([^"]+)"', text)
                    if not name_match:
                        name_match = re.search(r'<title>([^<]+?)(?:\s*-\s*YouTube)?</title>', text)

                    channel_name = name_match.group(1) if name_match else handle

                    return {
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "channel_url": f"https://www.youtube.com/channel/{channel_id}",
                        "uploads_playlist_id": "UU" + channel_id[2:],
                    }

            raise ValueError(f"Could not find channel ID for handle: {handle}")

    except httpx.HTTPError as e:
        raise ValueError(f"HTTP error resolving channel: {e}")


async def _fetch_channel_info(channel_id: str) -> dict:
    """Fetch channel info given a channel ID."""

    # If we have an API key, use it
    if settings.use_youtube_api:
        try:
            return await _fetch_channel_info_api(channel_id)
        except Exception as e:
            logger.warning(f"API fetch failed, falling back to scraping: {e}")

    # Fallback: scrape the channel page
    url = f"https://www.youtube.com/channel/{channel_id}"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }, timeout=15)
        resp.raise_for_status()

        text = resp.text
        name_match = re.search(r'"channelName"\s*:\s*"([^"]+)"', text)
        if not name_match:
            name_match = re.search(r'"author"\s*:\s*"([^"]+)"', text)
        if not name_match:
            name_match = re.search(r'<title>([^<]+?)(?:\s*-\s*YouTube)?</title>', text)

        channel_name = name_match.group(1) if name_match else channel_id

        return {
            "channel_id": channel_id,
            "channel_name": channel_name,
            "channel_url": url,
            "uploads_playlist_id": "UU" + channel_id[2:],
        }


async def _fetch_channel_info_api(channel_id: str) -> dict:
    """Fetch channel info using YouTube Data API v3."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={
                "part": "snippet,contentDetails",
                "id": channel_id,
                "key": settings.YOUTUBE_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("items"):
            raise ValueError(f"Channel not found: {channel_id}")

        item = data["items"][0]
        return {
            "channel_id": channel_id,
            "channel_name": item["snippet"]["title"],
            "channel_url": f"https://www.youtube.com/channel/{channel_id}",
            "uploads_playlist_id": item["contentDetails"]["relatedPlaylists"]["uploads"],
        }


# ─── New Video Detection ─────────────────────────────────────────────────────

async def check_channel_for_new_videos(channel: dict) -> list[dict]:
    """Check a channel for new videos. Returns list of newly discovered video dicts."""
    if settings.use_youtube_api:
        try:
            return await _check_via_api(channel)
        except Exception as e:
            logger.warning(f"API check failed for {channel['channel_name']}, falling back to RSS: {e}")

    return await _check_via_rss(channel)


async def _check_via_api(channel: dict) -> list[dict]:
    """Check for new videos using YouTube Data API v3 playlistItems.list."""
    playlist_id = channel.get("uploads_playlist_id")
    if not playlist_id:
        playlist_id = "UU" + channel["channel_id"][2:]

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={
                "part": "snippet",
                "playlistId": playlist_id,
                "maxResults": 5,
                "key": settings.YOUTUBE_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

    new_videos = []
    from app.database import get_db
    db = await get_db()

    for item in data.get("items", []):
        video_id = item["snippet"]["resourceId"]["videoId"]
        title = item["snippet"]["title"]
        published_at = item["snippet"].get("publishedAt", "")

        # Check if we already have this video
        cursor = await db.execute(
            "SELECT id FROM videos WHERE youtube_video_id = ?", (video_id,)
        )
        if await cursor.fetchone():
            continue

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        await db.execute(
            """INSERT INTO videos (channel_id, youtube_video_id, title, video_url, published_at)
               VALUES (?, ?, ?, ?, ?)""",
            (channel["id"], video_id, title, video_url, published_at),
        )
        new_videos.append({
            "youtube_video_id": video_id,
            "title": title,
            "video_url": video_url,
        })

        logger.info(f"New video detected: {title} ({video_id})")

        # Broadcast via WebSocket
        from app.routers.ws import broadcast
        await broadcast("new_video_detected", {
            "video_id": video_id,
            "title": title,
            "channel": channel["channel_name"],
        })

    if new_videos:
        await db.commit()

    return new_videos


async def _check_via_rss(channel: dict) -> list[dict]:
    """Check for new videos using YouTube RSS/Atom feed."""
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['channel_id']}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(feed_url, timeout=15)
        resp.raise_for_status()

    feed = feedparser.parse(resp.text)

    new_videos = []
    from app.database import get_db
    db = await get_db()

    for entry in feed.entries[:10]:  # Check last 10 entries
        video_id = entry.get("yt_videoid", "")
        if not video_id:
            continue

        title = entry.get("title", "Unknown")
        published_at = entry.get("published", "")

        # Check if we already have this video
        cursor = await db.execute(
            "SELECT id FROM videos WHERE youtube_video_id = ?", (video_id,)
        )
        if await cursor.fetchone():
            continue

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        await db.execute(
            """INSERT INTO videos (channel_id, youtube_video_id, title, video_url, published_at)
               VALUES (?, ?, ?, ?, ?)""",
            (channel["id"], video_id, title, video_url, published_at),
        )
        new_videos.append({
            "youtube_video_id": video_id,
            "title": title,
            "video_url": video_url,
        })

        logger.info(f"New video detected (RSS): {title} ({video_id})")

        # Broadcast via WebSocket
        from app.routers.ws import broadcast
        await broadcast("new_video_detected", {
            "video_id": video_id,
            "title": title,
            "channel": channel["channel_name"],
        })

    if new_videos:
        await db.commit()

    return new_videos
