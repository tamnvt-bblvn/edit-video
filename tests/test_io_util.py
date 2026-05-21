from __future__ import annotations

from edit_video.web.io_util import unique_edited_mp4_arcname


def test_unique_edited_mp4_arcname_no_collision() -> None:
    used: set[str] = set()
    assert unique_edited_mp4_arcname("clip.mp4", used) == "clip_edited.mp4"
    assert used == {"clip_edited.mp4"}


def test_unique_edited_mp4_arcname_collision_suffix() -> None:
    used: set[str] = {"clip_edited.mp4"}
    assert unique_edited_mp4_arcname("clip.mp4", used) == "clip_edited_2.mp4"
    assert unique_edited_mp4_arcname("clip.mp4", used) == "clip_edited_3.mp4"
