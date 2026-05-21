"""Edit video: scale, speed change, logo overlay via FFmpeg."""

from edit_video._version import package_version
from edit_video.exceptions import EditVideoError, FfprobeError, ToolNotFoundError
from edit_video.process import ProcessVideoResult, process_video

__version__ = package_version()

__all__ = [
    "EditVideoError",
    "FfprobeError",
    "ProcessVideoResult",
    "ToolNotFoundError",
    "__version__",
    "package_version",
    "process_video",
]
