from __future__ import annotations

import math

import pytest

from edit_video.ffmpeg import (
    build_filter_complex,
    logo_overlay_xy_expr,
    logo_scale_to_max_side_filter,
    split_atempo_chain,
)


def test_logo_overlay_xy_expr_corners() -> None:
    assert logo_overlay_xy_expr("tl", 3, 4) == "3:4"
    assert logo_overlay_xy_expr("tr", 10, 12) == "main_w-overlay_w-10:12"
    assert logo_overlay_xy_expr("bl", 5, 6) == "5:main_h-overlay_h-6"
    assert logo_overlay_xy_expr("br", 1, 2) == "main_w-overlay_w-1:main_h-overlay_h-2"


@pytest.mark.parametrize(
    ("speed", "want_product"),
    [
        (1.0, 1.0),
        (2.0, 2.0),
        (4.0, 4.0),
        (0.25, 0.25),
        (3.0, 3.0),
        (0.75, 0.75),
    ],
)
def test_split_atempo_chain_product(speed: float, want_product: float) -> None:
    chain = split_atempo_chain(speed)
    prod = math.prod(chain)
    assert math.isclose(prod, want_product, rel_tol=1e-9, abs_tol=1e-9)
    for f in chain:
        assert 0.499 <= f <= 2.001


def test_split_atempo_chain_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        split_atempo_chain(0)
    with pytest.raises(ValueError, match="positive"):
        split_atempo_chain(-1)


@pytest.mark.parametrize("has_audio", [True, False])
def test_build_filter_complex_maps(has_audio: bool) -> None:
    fc, maps = build_filter_complex(
        scale_w=640,
        scale_h=360,
        speed=2.0,
        overlay_x=5,
        overlay_y=8,
        has_audio=has_audio,
        frame_style="pad",
        logo_anchor="tl",
        logo_max_side=160,
    )
    assert (
        "[0:v]scale=640:360:force_original_aspect_ratio=decrease:"
        "force_divisible_by=2[scaled]"
    ) in fc
    assert "pad=640:360:(ow-iw)/2:(oh-ih)/2:black" in fc
    want_logo = (
        "[1:v]scale=w='if(gt(iw\\,ih)\\,160\\,-2)':h='if(gt(iw\\,ih)\\,-2\\,160)'"
        ":force_divisible_by=2,setsar=1[logo]"
    )
    assert want_logo in fc
    assert "[scaled][logo]overlay=5:8[wm]" in fc
    assert "[wm]pad=640:360:(ow-iw)/2:(oh-ih)/2:black,setsar=1,setpts=0.5*PTS[outv]" in fc
    assert "-map" in maps or "[" in "".join(maps)
    assert "[outv]" in maps
    if has_audio:
        assert "[0:a]" in fc and "[outa]" in fc
        assert maps.count("-map") == 2


def test_build_filter_complex_chains_audio_for_four_x() -> None:
    fc, _ = build_filter_complex(
        scale_w=128,
        scale_h=128,
        speed=4.0,
        overlay_x=0,
        overlay_y=0,
        has_audio=True,
        frame_style="pad",
        logo_anchor="tl",
        logo_max_side=160,
    )
    assert fc.count("atempo") == 2


def test_build_filter_complex_volume_db_applies_volume_filter() -> None:
    fc, _ = build_filter_complex(
        scale_w=640,
        scale_h=360,
        speed=2.0,
        overlay_x=0,
        overlay_y=0,
        has_audio=True,
        volume_db=-6.0,
        frame_style="pad",
        logo_anchor="tl",
        logo_max_side=160,
    )
    assert "[apre]volume=-6.0dB[outa]" in fc


def test_build_filter_complex_logo_max_side_zero_keeps_native_pixels() -> None:
    fc, _ = build_filter_complex(
        scale_w=640,
        scale_h=360,
        speed=1.0,
        overlay_x=0,
        overlay_y=0,
        has_audio=False,
        logo_max_side=0,
        frame_style="pad",
        logo_anchor="tl",
    )
    assert "[1:v]setsar=1[logo]" in fc
    assert "gt(iw" not in fc


def test_logo_scale_to_max_side_filter_targets_longest_side() -> None:
    s = logo_scale_to_max_side_filter(160)
    assert "160" in s
    assert "if(gt(iw" in s


def test_logo_scale_to_max_side_filter_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        logo_scale_to_max_side_filter(0)
    fc, _ = build_filter_complex(
        scale_w=640,
        scale_h=360,
        speed=2.0,
        overlay_x=0,
        overlay_y=0,
        has_audio=True,
        volume_db=0.0,
        frame_style="pad",
        logo_anchor="tl",
        logo_max_side=160,
    )
    assert "volume=" not in fc


def test_build_filter_complex_blur_fill_default_like_sample() -> None:
    fc, _ = build_filter_complex(
        scale_w=1920,
        scale_h=1080,
        speed=1.0,
        overlay_x=12,
        overlay_y=12,
        has_audio=False,
        frame_style="blur",
        blur_sigma=26.0,
        logo_anchor="tr",
        logo_max_side=120,
    )
    assert "[0:v]split=2[vbg][vfg]" in fc
    assert "gblur=sigma=26:steps=3" in fc
    assert "[scaled][logo]overlay=main_w-overlay_w-12:12[wm]" in fc
    assert "[bg][wm]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2,setsar=1[outv]" in fc


def test_build_filter_complex_stretch_scales_to_exact_frame() -> None:
    fc, _ = build_filter_complex(
        scale_w=640,
        scale_h=480,
        speed=1.0,
        overlay_x=3,
        overlay_y=4,
        has_audio=False,
        frame_style="stretch",
        logo_anchor="tl",
        logo_max_side=80,
    )
    assert "[0:v]scale=640:480:force_divisible_by=2,setsar=1[scaled]" in fc
    assert "gblur" not in fc
    assert "pad=" not in fc
    assert "[scaled][logo]overlay=3:4[wm]" in fc
    assert "[wm]setsar=1,setpts=1.0*PTS[outv]" in fc


def test_build_filter_complex_rejects_unknown_frame_style() -> None:
    with pytest.raises(ValueError, match="frame_style"):
        build_filter_complex(
            scale_w=640,
            scale_h=480,
            speed=1.0,
            overlay_x=0,
            overlay_y=0,
            has_audio=False,
            frame_style="cinema",
            logo_anchor="tl",
            logo_max_side=120,
        )
