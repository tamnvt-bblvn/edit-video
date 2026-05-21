from __future__ import annotations

import logging
import os
from pathlib import Path

import uvicorn

import edit_video
from edit_video.web.config import log_level, uvicorn_bind


def _reload_enabled() -> bool:
    raw = os.environ.get("EDIT_VIDEO_RELOAD")
    if raw is None:
        return True
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _reload_dirs() -> list[str]:
    pkg_dir = Path(edit_video.__file__).resolve().parent
    return [str(pkg_dir)]


def main() -> None:
    level = log_level()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    host, port = uvicorn_bind()
    uv_log = logging.getLevelName(level).lower()
    if _reload_enabled():
        uvicorn.run(
            "edit_video.web.app:app",
            host=host,
            port=port,
            reload=True,
            reload_dirs=_reload_dirs(),
            log_level=uv_log,
        )
    else:
        uvicorn.run(
            "edit_video.web.app:app",
            host=host,
            port=port,
            reload=False,
            log_level=uv_log,
        )


if __name__ == "__main__":
    main()
