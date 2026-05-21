from __future__ import annotations

import pytest

from edit_video.logo_scale import resolve_logo_max_side_for_frame


def test_pct_mode_matches_long_side_fraction() -> None:
    # max(1920,1080)=1920, 10% -> 192 -> even
    assert (
        resolve_logo_max_side_for_frame(
            frame_w=1920,
            frame_h=1080,
            logo_max_side=999,
            logo_max_side_pct=10.0,
        )
        == 192
    )


def test_pct_mode_swapped_dimensions_matches() -> None:
    """1080x1920 vs 1920x1080: same max side -> identical logo box."""
    a = resolve_logo_max_side_for_frame(
        frame_w=1080,
        frame_h=1920,
        logo_max_side=0,
        logo_max_side_pct=12.0,
    )
    b = resolve_logo_max_side_for_frame(
        frame_w=1920,
        frame_h=1080,
        logo_max_side=0,
        logo_max_side_pct=12.0,
    )
    assert a == b == 230


def test_pct_mode_rounds_to_even_within_bounds() -> None:
    assert (
        resolve_logo_max_side_for_frame(
            frame_w=1920,
            frame_h=1080,
            logo_max_side=0,
            logo_max_side_pct=10.5,
        )
        == 202
    )


def test_px_mode_when_pct_zero() -> None:
    assert (
        resolve_logo_max_side_for_frame(
            frame_w=1920,
            frame_h=1080,
            logo_max_side=120,
            logo_max_side_pct=0.0,
        )
        == 120
    )


def test_px_mode_zero_keeps_native_semantics() -> None:
    assert (
        resolve_logo_max_side_for_frame(
            frame_w=640,
            frame_h=480,
            logo_max_side=0,
            logo_max_side_pct=0.0,
        )
        == 0
    )


def test_tiny_frame_clamps_to_min_even() -> None:
    assert (
        resolve_logo_max_side_for_frame(
            frame_w=100,
            frame_h=100,
            logo_max_side=0,
            logo_max_side_pct=1.0,
        )
        == 2
    )


def test_rejects_non_finite_pct() -> None:
    with pytest.raises(ValueError, match="finite"):
        resolve_logo_max_side_for_frame(
            frame_w=640,
            frame_h=480,
            logo_max_side=120,
            logo_max_side_pct=float("nan"),
        )


def test_rejects_pct_out_of_range() -> None:
    with pytest.raises(ValueError, match="between 0 and 50"):
        resolve_logo_max_side_for_frame(
            frame_w=640,
            frame_h=480,
            logo_max_side=120,
            logo_max_side_pct=51.0,
        )
