from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__all__ = ["package_version"]


def package_version() -> str:
    try:
        return version("edit-video")
    except PackageNotFoundError:
        return "0.0.0+unknown"
