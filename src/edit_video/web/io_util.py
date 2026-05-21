from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException, UploadFile

_VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"}
_LOGO_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def allowed_suffix(upload: UploadFile, allowed: set[str]) -> str:
    raw = Path(upload.filename or "").suffix.lower()
    if raw not in allowed:
        kinds = ", ".join(sorted(e.lstrip(".").upper() for e in allowed))
        raise HTTPException(
            status_code=400,
            detail=f"Định dạng không được hỗ trợ ({kinds}). "
            f"File: {upload.filename or '(không có tên)'}",
        )
    return raw


_SAFE_STEM = re.compile(r"[^\w\-]+", re.UNICODE)


def safe_download_stem(name: str | None) -> str:
    stem = Path(name or "video").stem
    stem = _SAFE_STEM.sub("_", stem)
    return stem[:80] if stem else "video"


def unique_edited_mp4_arcname(original_filename: str | None, used: set[str]) -> str:
    """Stable ZIP entry name for an edited video; avoids collisions inside one archive."""
    stem_base = safe_download_stem(original_filename)
    candidate = f"{stem_base}_edited.mp4"
    if candidate not in used:
        used.add(candidate)
        return candidate
    i = 2
    while True:
        c = f"{stem_base}_edited_{i}.mp4"
        if c not in used:
            used.add(c)
            return c
        i += 1


async def stream_upload_to_path(upload: UploadFile, dest: Path, *, max_bytes: int) -> None:
    wrote = 0
    chunk = 1024 * 1024
    try:
        with dest.open("wb") as f:
            while True:
                block = await upload.read(chunk)
                if not block:
                    break
                wrote += len(block)
                if wrote > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="File vượt quá giới hạn kích thước tải lên "
                        f"({max_bytes // (1024 * 1024)} MB).",
                    )
                f.write(block)
    except HTTPException:
        if dest.is_file():
            dest.unlink(missing_ok=True)
        raise
    if wrote == 0:
        if dest.is_file():
            dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="File tải lên rỗng.")


def video_extensions() -> set[str]:
    return set(_VIDEO_EXT)


def logo_extensions() -> set[str]:
    return set(_LOGO_EXT)
