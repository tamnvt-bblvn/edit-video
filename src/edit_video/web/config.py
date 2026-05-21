from __future__ import annotations

import logging
import os


def env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def max_upload_bytes() -> int:
    mb = env_int("EDIT_VIDEO_MAX_UPLOAD_MB", 500)
    if mb < 1:
        mb = 1
    return mb * 1024 * 1024


def max_batch_videos() -> int:
    n = env_int("EDIT_VIDEO_MAX_BATCH", 25)
    return max(1, min(n, 500))


def batch_encode_workers() -> int:
    """Số job FFmpeg chạy song song trong một request batch (mỗi job một luồng)."""
    raw = os.environ.get("EDIT_VIDEO_BATCH_WORKERS")
    if raw is None:
        cpus = os.cpu_count() or 1
        return max(1, min(4, cpus))
    n = env_int("EDIT_VIDEO_BATCH_WORKERS", 4)
    return max(1, min(n, 32))


def log_level() -> int:
    raw = os.environ.get("EDIT_VIDEO_LOG_LEVEL", "INFO").strip().upper()
    return getattr(logging, raw, logging.INFO)


def ffmpeg_verbose_from_env() -> bool:
    """Khi bật: ffmpeg không redirect stderr → có tiến độ khung hình trực tiếp trên console."""
    return (
        os.environ.get("EDIT_VIDEO_FFMPEG_VERBOSE", "").strip().lower()
        in ("1", "true", "yes", "on")
    )


def uvicorn_bind() -> tuple[str, int]:
    # 0.0.0.0 = listen on all interfaces so LAN devices can reach http://<this-pc-ip>:port
    host = os.environ.get("EDIT_VIDEO_HOST", "0.0.0.0")
    port = env_int("EDIT_VIDEO_PORT", 8008)
    if not (1 <= port <= 65535):
        port = 8008
    return host, port
