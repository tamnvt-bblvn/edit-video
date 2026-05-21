"""Domain errors for the edit-video toolkit."""


class EditVideoError(Exception):
    """Base class for actionable edit-video failures."""


class ToolNotFoundError(EditVideoError):
    """ffmpeg or ffprobe is missing from PATH."""


class FfprobeError(EditVideoError):
    """ffprobe failed or returned invalid data."""
