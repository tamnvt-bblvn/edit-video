from __future__ import annotations

import pytest

from edit_video.cli import build_parser


def test_version_exits_zero() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--version"])
    assert exc.value.code == 0


def test_requires_core_options() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
