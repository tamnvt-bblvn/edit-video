from __future__ import annotations

import pytest

from edit_video.web.config import batch_encode_workers


def test_batch_encode_workers_default_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EDIT_VIDEO_BATCH_WORKERS", raising=False)
    monkeypatch.setattr("edit_video.web.config.os.cpu_count", lambda: 64)
    assert batch_encode_workers() == 4


def test_batch_encode_workers_env_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDIT_VIDEO_BATCH_WORKERS", "8")
    assert batch_encode_workers() == 8

    monkeypatch.setenv("EDIT_VIDEO_BATCH_WORKERS", "99")
    assert batch_encode_workers() == 32

    monkeypatch.setenv("EDIT_VIDEO_BATCH_WORKERS", "0")
    assert batch_encode_workers() == 1
