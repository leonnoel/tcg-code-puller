"""Video processing pipeline — download, extract frames, scan for codes."""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import cv2

from app.config import settings
from app.services.qr_scanner import scan_frame_for_qr
from app.services.ocr_scanner import scan_frame_for_text_codes
from app.services.code_validator import validate_code

logger = logging.getLogger(__name__)

# Thread pool for CPU-bound frame scanning
_executor = ThreadPoolExecutor(max_workers=4)


async def process_video(video: dict) -> None:
    """Full processing pipeline for a video.

    1. Download video
    2. Extract frames
    3. Scan frames for QR codes and OCR
    4. Validate and store codes
    5. Cleanup
    """
    from app.database import get_db
    from app.routers.ws import broadcast

    db = await get_db()
    video_id = video["id"]
    video_path = None

    try:
        # Update status to downloading
        await db.execute(
            "UPDATE videos SET status = 'downloading', processing_started_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), video_id),
        )
        await db.commit()

        await broadcast("processing_started", {
            "video_id": video["youtube_video_id"],
            "title": video["title"],
            "stage": "downloading",
        })

        # Step 1: Download video
        logger.info(f"Downloading: {video['title']}")
        video_path = await download_video(video["video_url"], video["youtube_video_id"])

        if not video_path or not os.path.exists(video_path):
            raise RuntimeError("Download failed — no file produced")

        # Update status to processing
        await db.execute(
            "UPDATE videos SET status = 'processing' WHERE id = ?", (video_id,)
        )
        await db.commit()

        await broadcast("processing_started", {
            "video_id": video["youtube_video_id"],
            "title": video["title"],
            "stage": "extracting_frames",
        })

        # Step 2: Extract frames
        logger.info(f"Extracting frames from: {video['title']}")
        frames_dir = settings.FRAMES_DIR / video["youtube_video_id"]
        frames_dir.mkdir(parents=True, exist_ok=True)

        frame_count = await extract_frames(video_path, str(frames_dir), settings.FRAME_INTERVAL)

        await db.execute(
            "UPDATE videos SET frames_extracted = ? WHERE id = ?", (frame_count, video_id)
        )
        await db.commit()

        logger.info(f"Extracted {frame_count} frames from: {video['title']}")

        await broadcast("processing_started", {
            "video_id": video["youtube_video_id"],
            "title": video["title"],
            "stage": "scanning",
            "frame_count": frame_count,
        })

        # Step 3: Scan frames — two-pass approach
        # Pass 1: Fast QR scan on all frames
        # Pass 2: OCR only on frames near QR hits (±5 frames) to reduce false positives
        scan_started = datetime.utcnow()
        qr_found = 0
        ocr_found = 0
        unique_codes = set()

        frame_files = sorted(frames_dir.glob("*.jpg"))
        total_frames = len(frame_files)

        # ── Pass 1: QR scan (fast) ──
        qr_hit_indices = set()
        for i, frame_path in enumerate(frame_files):
            try:
                codes_from_frame = await asyncio.get_event_loop().run_in_executor(
                    _executor, _scan_frame_qr_only, str(frame_path)
                )
                for code_info in codes_from_frame:
                    qr_hit_indices.add(i)
                    code_normalized = code_info["code"]
                    if code_normalized not in unique_codes:
                        unique_codes.add(code_normalized)
                        qr_found += 1
                        frame_timestamp = _get_frame_timestamp(frame_path.name)
                        await _store_and_broadcast_code(
                            db, video_id, video, code_info, frame_timestamp, str(frame_path), broadcast
                        )
            except Exception as e:
                logger.warning(f"QR scan error {frame_path.name}: {e}")

            if (i + 1) % 200 == 0:
                logger.info(f"QR pass: {i+1}/{total_frames} frames, {qr_found} QR codes found")

        logger.info(f"QR pass complete: {qr_found} codes from {total_frames} frames")

        # ── Pass 2: OCR scan (slower, targeted) ──
        # Only scan frames near where QR codes were found (±10 frames)
        # This avoids OCR false positives from random text in non-card frames
        if qr_hit_indices:
            ocr_indices = set()
            for idx in qr_hit_indices:
                for offset in range(-10, 11):
                    target = idx + offset
                    if 0 <= target < total_frames:
                        ocr_indices.add(target)
            ocr_frames = sorted(ocr_indices)
        else:
            # No QR found — run OCR on a sample of frames (every 5th frame)
            # to avoid massive false positives on non-pack-opening videos
            ocr_frames = list(range(0, total_frames, 5))

        for i in ocr_frames:
            frame_path = frame_files[i]
            try:
                codes_from_frame = await asyncio.get_event_loop().run_in_executor(
                    _executor, _scan_frame_ocr_only, str(frame_path)
                )
                for code_info in codes_from_frame:
                    code_normalized = code_info["code"]
                    if code_normalized not in unique_codes:
                        unique_codes.add(code_normalized)
                        ocr_found += 1
                        frame_timestamp = _get_frame_timestamp(frame_path.name)
                        await _store_and_broadcast_code(
                            db, video_id, video, code_info, frame_timestamp, str(frame_path), broadcast
                        )
            except Exception as e:
                logger.warning(f"OCR scan error {frame_path.name}: {e}")

        logger.info(f"OCR pass complete: {ocr_found} additional codes from {len(ocr_frames)} frames")

        # Step 4: Record scan log
        scan_completed = datetime.utcnow()
        await db.execute(
            """INSERT INTO scan_logs
               (video_id, started_at, completed_at, frames_scanned, qr_codes_found, ocr_codes_found, total_unique_codes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                video_id,
                scan_started.isoformat(),
                scan_completed.isoformat(),
                total_frames,
                qr_found,
                ocr_found,
                len(unique_codes),
            ),
        )

        # Update video status
        await db.execute(
            "UPDATE videos SET status = 'completed', processing_completed_at = ? WHERE id = ?",
            (scan_completed.isoformat(), video_id),
        )
        await db.commit()

        logger.info(
            f"Completed processing: {video['title']} — "
            f"{total_frames} frames scanned, {len(unique_codes)} codes found "
            f"({qr_found} QR, {ocr_found} OCR)"
        )

        await broadcast("processing_completed", {
            "video_id": video["youtube_video_id"],
            "title": video["title"],
            "codes_found": len(unique_codes),
            "frames_scanned": total_frames,
        })

    except Exception as e:
        logger.error(f"Error processing video {video['title']}: {e}")
        await db.execute(
            "UPDATE videos SET status = 'failed', error_message = ? WHERE id = ?",
            (str(e)[:500], video_id),
        )
        await db.commit()

        await broadcast("processing_failed", {
            "video_id": video["youtube_video_id"],
            "title": video["title"],
            "error": str(e)[:200],
        })

    finally:
        # Cleanup downloaded video (keep frames for now)
        if video_path and os.path.exists(video_path):
            try:
                os.unlink(video_path)
                logger.debug(f"Cleaned up video file: {video_path}")
            except Exception:
                pass


def _scan_frame_qr_only(frame_path: str) -> list[dict]:
    """Scan a single frame for QR codes only (fast). Runs in thread pool."""
    codes = []
    try:
        frame = cv2.imread(frame_path)
        if frame is None:
            return codes
        qr_results = scan_frame_for_qr(frame)
        for qr_data in qr_results:
            validated = validate_code(qr_data)
            if validated:
                codes.append({
                    "code": validated,
                    "raw": qr_data,
                    "source": "qr",
                    "confidence": 1.0,
                })
    except Exception as e:
        logger.debug(f"QR scan error {frame_path}: {e}")
    return codes


def _scan_frame_ocr_only(frame_path: str) -> list[dict]:
    """Scan a single frame for text codes via OCR (slower). Runs in thread pool."""
    codes = []
    try:
        frame = cv2.imread(frame_path)
        if frame is None:
            return codes
        ocr_results = scan_frame_for_text_codes(frame)
        for ocr_code in ocr_results:
            validated = validate_code(ocr_code)
            if validated:
                codes.append({
                    "code": validated,
                    "raw": ocr_code,
                    "source": "ocr",
                    "confidence": 0.7,
                })
    except Exception as e:
        logger.debug(f"OCR scan error {frame_path}: {e}")
    return codes


def _scan_single_frame(frame_path: str) -> list[dict]:
    """Scan a single frame for codes (QR + OCR). Used for testing."""
    codes = _scan_frame_qr_only(frame_path)
    found_qr_codes = {c["code"] for c in codes}
    ocr_codes = _scan_frame_ocr_only(frame_path)
    for c in ocr_codes:
        if c["code"] not in found_qr_codes:
            codes.append(c)
    return codes


async def _store_and_broadcast_code(db, video_id, video, code_info, frame_timestamp, frame_path, broadcast):
    """Store a found code in the DB and broadcast via WebSocket."""
    code_normalized = code_info["code"]
    try:
        await db.execute(
            """INSERT OR IGNORE INTO codes
               (video_id, code, code_normalized, source_type, frame_timestamp, frame_path, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                video_id,
                code_info.get("raw", code_normalized),
                code_normalized,
                code_info["source"],
                frame_timestamp,
                frame_path,
                code_info.get("confidence", 1.0),
            ),
        )
        await db.commit()

        logger.info(
            f"CODE FOUND [{code_info['source'].upper()}]: {code_normalized} "
            f"in {video['title']} at ~{frame_timestamp:.1f}s"
        )

        await broadcast("code_found", {
            "code": code_normalized,
            "source": code_info["source"],
            "video_title": video["title"],
            "video_id": video["youtube_video_id"],
            "frame_timestamp": frame_timestamp,
        })
    except Exception as e:
        logger.debug(f"Duplicate or insert error: {e}")


def _get_frame_timestamp(filename: str) -> float:
    """Extract approximate timestamp from frame filename (frame_NNNNNN.jpg).

    ffmpeg numbering starts at 1, so frame_000001.jpg = 0.0s, frame_000002.jpg = 0.5s, etc.
    """
    try:
        # Filename format: frame_000001.jpg
        num = int(filename.split("_")[1].split(".")[0])
        return (num - 1) * settings.FRAME_INTERVAL
    except (IndexError, ValueError):
        return 0.0


async def download_video(video_url: str, video_id: str) -> str:
    """Download a YouTube video using yt-dlp.

    Returns path to the downloaded video file.
    """
    output_path = str(settings.VIDEOS_DIR / f"{video_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", f"bestvideo[height<={settings.VIDEO_MAX_RESOLUTION}]+bestaudio/best[height<={settings.VIDEO_MAX_RESOLUTION}]",
        "--merge-output-format", "mp4",
        "-o", output_path,
        "--no-warnings",
        "--quiet",
        "--no-progress",
    ]

    # Add cookie authentication if configured
    if settings.YTDLP_COOKIES_FILE:
        cmd.extend(["--cookies", settings.YTDLP_COOKIES_FILE])
    elif settings.YTDLP_COOKIES_FROM_BROWSER:
        cmd.extend(["--cookies-from-browser", settings.YTDLP_COOKIES_FROM_BROWSER])

    # Optionally download only the first N minutes for faster scanning
    if settings.SCAN_FIRST_MINUTES > 0:
        seconds = settings.SCAN_FIRST_MINUTES * 60
        cmd.extend(["--download-sections", f"*0-{seconds}"])

    cmd.append(video_url)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await asyncio.wait_for(
        process.communicate(),
        timeout=settings.PROCESS_TIMEOUT,
    )

    if process.returncode != 0:
        error = stderr.decode().strip() if stderr else "Unknown download error"
        raise RuntimeError(f"yt-dlp failed (exit {process.returncode}): {error}")

    # Find the actual output file
    expected = settings.VIDEOS_DIR / f"{video_id}.mp4"
    if expected.exists():
        return str(expected)

    # Try to find any file matching the video ID
    for f in settings.VIDEOS_DIR.iterdir():
        if f.name.startswith(video_id) and f.is_file():
            return str(f)

    raise RuntimeError("Downloaded file not found")


async def extract_frames(video_path: str, output_dir: str, interval: float = 0.5) -> int:
    """Extract frames from a video at the given interval using ffmpeg.

    Returns number of frames extracted.
    """
    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vf", f"fps=1/{interval}",
        "-q:v", "2",  # High quality JPEG
        "-vsync", "vfr",
        os.path.join(output_dir, "frame_%06d.jpg"),
        "-y",  # Overwrite
        "-loglevel", "error",
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await asyncio.wait_for(
        process.communicate(),
        timeout=settings.PROCESS_TIMEOUT,
    )

    if process.returncode != 0:
        error = stderr.decode().strip() if stderr else "Unknown ffmpeg error"
        raise RuntimeError(f"ffmpeg failed (exit {process.returncode}): {error}")

    # Count extracted frames
    frame_count = len([f for f in os.listdir(output_dir) if f.endswith(".jpg")])
    return frame_count
