"""Application configuration."""

import os
from pathlib import Path


class Settings:
    """Application settings loaded from environment variables with sensible defaults."""

    # Base paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    DB_PATH: Path = DATA_DIR / "pokemon_tcg.db"
    VIDEOS_DIR: Path = DATA_DIR / "videos"
    FRAMES_DIR: Path = DATA_DIR / "frames"

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # YouTube Data API v3 (optional — enables fast polling)
    YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")

    # Polling intervals (seconds)
    API_POLL_INTERVAL: int = int(os.getenv("API_POLL_INTERVAL", "30"))
    RSS_POLL_INTERVAL: int = int(os.getenv("RSS_POLL_INTERVAL", "120"))

    # Video processing
    VIDEO_MAX_RESOLUTION: str = os.getenv("VIDEO_MAX_RESOLUTION", "720")
    FRAME_INTERVAL: float = float(os.getenv("FRAME_INTERVAL", "0.5"))
    MAX_CONCURRENT_DOWNLOADS: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2"))
    MAX_VIDEO_DURATION: int = int(os.getenv("MAX_VIDEO_DURATION", "7200"))  # 2 hours

    # Cleanup
    VIDEO_RETENTION_HOURS: int = int(os.getenv("VIDEO_RETENTION_HOURS", "1"))
    FRAME_RETENTION_HOURS: int = int(os.getenv("FRAME_RETENTION_HOURS", "24"))

    # Processing
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    PROCESS_TIMEOUT: int = int(os.getenv("PROCESS_TIMEOUT", "1800"))  # 30 minutes

    # yt-dlp cookies for YouTube authentication
    # Can be a path to a Netscape cookies.txt file or a browser name (e.g., "chrome", "firefox")
    YTDLP_COOKIES_FILE: str = os.getenv("YTDLP_COOKIES_FILE", "")
    YTDLP_COOKIES_FROM_BROWSER: str = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "")

    @property
    def use_youtube_api(self) -> bool:
        """Whether YouTube Data API is configured."""
        return bool(self.YOUTUBE_API_KEY)

    @property
    def poll_interval(self) -> int:
        """Active polling interval based on configuration."""
        return self.API_POLL_INTERVAL if self.use_youtube_api else self.RSS_POLL_INTERVAL

    def ensure_directories(self) -> None:
        """Create required data directories."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        self.FRAMES_DIR.mkdir(parents=True, exist_ok=True)

        # Auto-detect cookies.txt in data directory
        if not self.YTDLP_COOKIES_FILE:
            cookies_path = self.DATA_DIR / "cookies.txt"
            if cookies_path.exists():
                self.YTDLP_COOKIES_FILE = str(cookies_path)


settings = Settings()
