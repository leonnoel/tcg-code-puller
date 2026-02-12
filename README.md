# Pokemon TCG Code Monitor ⚡

Automatically monitors Pokémon pack-opening YouTubers for TCG redemption codes. When a new video is uploaded, it downloads the video, scans every frame for QR codes and printed codes, and presents them in a live dashboard so you can redeem them first.

## Features

- **YouTube Channel Monitoring** — Add channels by URL, handle, or ID
- **Dual Detection** — YouTube Data API polling (30s) + RSS fallback (2min)
- **QR Code Scanning** — Detects QR codes from video frames using pyzbar
- **OCR Fallback** — Reads printed codes using Tesseract OCR
- **Live Dashboard** — Real-time WebSocket notifications when codes are found
- **One-Click Copy** — Copy codes instantly to redeem on pokemon.com
- **Dark Theme UI** — Clean, responsive interface with 4 tabs

## Quick Start

```bash
# 1. Install system dependencies
chmod +x install.sh && bash install.sh

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. (Optional) Set YouTube API key for faster polling
export YOUTUBE_API_KEY="your-api-key-here"

# 4. Start the app
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000 in your browser.

## Monitoring Modes

| Mode | Poll Interval | Requirements |
|------|--------------|-------------|
| **YouTube API** (recommended) | 30 seconds | Free Google API key |
| **RSS Feed** (fallback) | 2 minutes | None |

### Getting a YouTube API Key (free)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable "YouTube Data API v3"
3. Create an API key (no OAuth needed)
4. Set it: `export YOUTUBE_API_KEY="your-key"`

## Configuration

All settings via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `YOUTUBE_API_KEY` | (none) | YouTube Data API key for fast polling |
| `API_POLL_INTERVAL` | `30` | Seconds between API polls |
| `RSS_POLL_INTERVAL` | `120` | Seconds between RSS polls |
| `VIDEO_MAX_RESOLUTION` | `720` | Max video download resolution |
| `FRAME_INTERVAL` | `0.5` | Seconds between frame extractions |
| `SCAN_FIRST_MINUTES` | `0` | Only scan first N minutes of video (0 = full) |
| `PORT` | `8000` | Server port |
| `YTDLP_COOKIES_FILE` | (none) | Path to Netscape cookies.txt for YouTube auth |
| `YTDLP_COOKIES_FROM_BROWSER` | (none) | Browser to extract cookies from (e.g., `chrome`) |

## How It Works

1. **Monitor** — Polls YouTube channels for new video uploads
2. **Download** — Grabs the video at 720p via yt-dlp
3. **Extract** — Pulls frames every 0.5 seconds using ffmpeg
4. **Scan** — Runs QR detection (pyzbar) then OCR (tesseract) on each frame
5. **Validate** — Matches against Pokémon TCG code format (13 alphanumeric chars)
6. **Notify** — Pushes codes to your browser via WebSocket in real-time

## ⚡ Speed Tips (Be First to Redeem)

1. **Use YouTube API key** — Detects new uploads in ~30 seconds vs ~2-15 minutes with RSS
2. **Set `SCAN_FIRST_MINUTES=5`** — Most pack openers show code cards in the first few minutes; scanning only the start is much faster
3. **Keep the dashboard open** — WebSocket pushes codes to your browser the instant they're found
4. **Enable desktop notifications** — Click the 🔔 bell so you get alerted even if the tab is in the background
5. **Use the "Process Video by URL" feature** — If you spot a pack opening video before the poller does, paste the URL directly

## YouTube Cookie Authentication

YouTube may block video downloads from headless/cloud environments. If you see "Sign in to confirm you're not a bot" errors, you need to provide cookies:

**Option 1: Export cookies from your browser** (recommended)
```bash
# Use a browser extension like "Get cookies.txt" to export YouTube cookies
export YTDLP_COOKIES_FILE="/path/to/cookies.txt"
```

**Option 2: Auto-extract from local browser**
```bash
# Works when running on the same machine as your browser
export YTDLP_COOKIES_FROM_BROWSER="chrome"  # or firefox, edge, etc.
```

## Tech Stack

- **Backend**: FastAPI + SQLite + APScheduler
- **Frontend**: Vanilla JS + Tailwind CSS
- **Video**: yt-dlp + ffmpeg
- **Vision**: OpenCV + pyzbar + pytesseract
