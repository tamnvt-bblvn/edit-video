from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from edit_video.web.app import create_app


def test_health() -> None:
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_index_contains_upload_form() -> None:
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200
    text = r.text
    assert 'id="videos"' in text
    assert 'id="logo"' in text
    assert 'data-w="1080" data-h="1920"' in text
    assert 'header-stats' in text
    assert "/api/process" in text
    assert 'name="logo_max_side_pct"' in text
