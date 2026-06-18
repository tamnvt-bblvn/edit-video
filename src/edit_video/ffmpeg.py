from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
from typing import Any

from edit_video.exceptions import FfprobeError, ToolNotFoundError

logger = logging.getLogger(__name__)

_FFPROBE_TIMEOUT_S = 60

FRAME_STYLES = frozenset({"blur", "pad", "stretch"})
LOGO_ANCHORS = frozenset({"tl", "tr", "bl", "br"})


def logo_scale_to_max_side_filter(max_side: int) -> str:
    """
    Scale logo so its **longest** side becomes ``max_side`` px (up or down), aspect kept.

    Unlike ``scale=W:H:force_original_aspect_ratio=decrease``, small raster logos are
    **upscaled** to the target box so manual output width/height + % logo still hit the
    intended on-screen size.
    """
    m = int(max_side)
    if m < 1:
        raise ValueError("max_side must be positive")
    # Expressions: commas escaped for filter_complex; -2 keeps aspect on the computed dim.
    return (
        f"scale=w='if(gt(iw\\,ih)\\,{m}\\,-2)':h='if(gt(iw\\,ih)\\,-2\\,{m})'"
        f":force_divisible_by=2"
    )


def logo_overlay_xy_expr(anchor: str, overlay_x: int, overlay_y: int) -> str:
    """FFmpeg overlay x:y from corner insets (px). tr/br: overlay_x counts from right edge."""
    a = anchor.strip().lower()
    ox, oy = int(overlay_x), int(overlay_y)
    if a == "tl":
        return f"{ox}:{oy}"
    if a == "tr":
        return f"main_w-overlay_w-{ox}:{oy}"
    if a == "bl":
        return f"{ox}:main_h-overlay_h-{oy}"
    if a == "br":
        return f"main_w-overlay_w-{ox}:main_h-overlay_h-{oy}"
    raise ValueError(f"logo_anchor must be one of {sorted(LOGO_ANCHORS)}, got {anchor!r}")


def ffmpeg_on_path() -> str | None:
    return shutil.which("ffmpeg")


def ffprobe_on_path() -> str | None:
    return shutil.which("ffprobe")


def ensure_tools() -> None:
    missing: list[str] = []
    if not ffmpeg_on_path():
        missing.append("ffmpeg")
    if not ffprobe_on_path():
        missing.append("ffprobe")
    if missing:
        raise ToolNotFoundError(
            "Required binaries not found on PATH: "
            + ", ".join(missing)
            + ". Install FFmpeg (bundles ffmpeg and ffprobe)."
        )


def probe_has_audio(input_path: str) -> bool:
    ffprobe = ffprobe_on_path()
    if not ffprobe:
        raise ToolNotFoundError("ffprobe not found on PATH.")
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "json",
        os.path.abspath(input_path),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=_FFPROBE_TIMEOUT_S,
        check=False,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise FfprobeError(
            "ffprobe failed" + (f": {stderr}" if stderr else f" (exit {proc.returncode})")
        )
    try:
        payload: dict[str, Any] = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise FfprobeError("ffprobe returned invalid JSON") from exc
    streams = payload.get("streams") or []
    return any(s.get("codec_type") == "audio" for s in streams)


def split_atempo_chain(speed: float, eps: float = 1e-9) -> list[float]:
    """Return atempo factors in [0.5, 2.0] whose product equals speed."""
    if speed <= 0:
        raise ValueError("speed must be positive")
    factors: list[float] = []
    remaining = speed
    while remaining > 2.0 + eps:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5 - eps:
        factors.append(0.5)
        remaining /= 0.5
    if not math.isclose(remaining, 1.0, rel_tol=1e-9, abs_tol=1e-6):
        factors.append(remaining)
    if not factors:
        factors.append(1.0)
    for f in factors:
        if f < 0.5 - eps or f > 2.0 + eps:
            raise ValueError(f"Internal atempo split error: {factors}")
    return factors


def build_filter_complex(
    *,
    scale_w: int,
    scale_h: int,
    speed: float,
    overlay_x: int,
    overlay_y: int,
    has_audio: bool,
    volume_db: float = 0.0,
    logo_max_side: int = 120,
    frame_style: str = "blur",
    blur_sigma: float = 26.0,
    logo_anchor: str = "tr",
    with_logo: bool = True,
) -> tuple[str, list[str]]:
    fs = frame_style.strip().lower()
    if fs not in FRAME_STYLES:
        raise ValueError(f"frame_style must be one of {sorted(FRAME_STYLES)}, got {frame_style!r}")
    anchor = logo_anchor.strip().lower()
    if anchor not in LOGO_ANCHORS:
        raise ValueError(f"logo_anchor must be one of {sorted(LOGO_ANCHORS)}, got {logo_anchor!r}")
    if blur_sigma < 0.5 or blur_sigma > 100.0:
        raise ValueError("blur_sigma must be between 0.5 and 100")

    W, H = scale_w, scale_h
    setpts = 1.0 / speed
    setpts_es = repr(setpts) if setpts.is_integer() else f"{setpts:.12g}"

    def _sigma_str(v: float) -> str:
        t = f"{v:.8f}".rstrip("0").rstrip(".")
        return t if t else "0"

    if with_logo:
        if logo_max_side <= 0:
            logo_chain = "[1:v]setsar=1[logo]"
        else:
            m = logo_max_side
            logo_chain = f"[1:v]{logo_scale_to_max_side_filter(m)},setsar=1[logo]"
        xy = logo_overlay_xy_expr(anchor, overlay_x, overlay_y)
        overlay_on_fg = f"[scaled][logo]overlay={xy}[wm]"

    if fs == "pad":
        scale_only = (
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease:"
            f"force_divisible_by=2[scaled]"
        )
        if with_logo:
            pad_pts = (
                f"[wm]pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,"
                f"setsar=1,setpts={setpts_es}*PTS[outv]"
            )
            parts: list[str] = [scale_only, logo_chain, overlay_on_fg, pad_pts]
        else:
            pad_pts = (
                f"[scaled]pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,"
                f"setsar=1,setpts={setpts_es}*PTS[outv]"
            )
            parts = [scale_only, pad_pts]
    elif fs == "stretch":
        stretch_full = (
            f"[0:v]scale={W}:{H}:force_divisible_by=2,setsar=1[scaled]"
        )
        if with_logo:
            out_pts = f"[wm]setsar=1,setpts={setpts_es}*PTS[outv]"
            parts = [stretch_full, logo_chain, overlay_on_fg, out_pts]
        else:
            out_pts = f"[scaled]setsar=1,setpts={setpts_es}*PTS[outv]"
            parts = [stretch_full, out_pts]
    else:
        sig = _sigma_str(float(blur_sigma))
        split_in = "[0:v]split=2[vbg][vfg]"
        bg_blur = (
            f"[vbg]scale={W}:{H}:force_original_aspect_ratio=increase:force_divisible_by=2,"
            f"crop={W}:{H}:(iw-{W})/2:(ih-{H})/2,"
            f"gblur=sigma={sig}:steps=3,setsar=1,setpts={setpts_es}*PTS[bg]"
        )
        fg_scale = (
            f"[vfg]scale={W}:{H}:force_original_aspect_ratio=decrease:"
            f"force_divisible_by=2,setsar=1,setpts={setpts_es}*PTS[scaled]"
        )
        if with_logo:
            stack_fg = (
                "[bg][wm]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2,setsar=1[outv]"
            )
            parts = [split_in, bg_blur, fg_scale, logo_chain, overlay_on_fg, stack_fg]
        else:
            stack_fg = (
                "[bg][scaled]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2,setsar=1[outv]"
            )
            parts = [split_in, bg_blur, fg_scale, stack_fg]

    maps: list[str] = ["-map", "[outv]"]

    if has_audio:
        atempos = split_atempo_chain(speed)
        apply_volume = not math.isclose(volume_db, 0.0, rel_tol=0.0, abs_tol=1e-9)
        if len(atempos) == 1:
            if apply_volume:
                parts.append(f"[0:a]atempo={atempos[0]}[apre]")
                parts.append(f"[apre]volume={volume_db}dB[outa]")
            else:
                parts.append(f"[0:a]atempo={atempos[0]}[outa]")
        else:
            parts.append(f"[0:a]atempo={atempos[0]}[at0]")
            for i in range(1, len(atempos) - 1):
                parts.append(f"[at{i - 1}]atempo={atempos[i]}[at{i}]")
            last = len(atempos) - 1
            if apply_volume:
                parts.append(f"[at{last - 1}]atempo={atempos[last]}[apre]")
                parts.append(f"[apre]volume={volume_db}dB[outa]")
            else:
                parts.append(f"[at{last - 1}]atempo={atempos[last]}[outa]")
        maps.extend(["-map", "[outa]"])

    return ";".join(parts), maps


def build_ffmpeg_command(
    *,
    input_path: str,
    output_path: str,
    logo_path: str | None,
    scale_w: int,
    scale_h: int,
    speed: float,
    overlay_x: int,
    overlay_y: int,
    has_audio: bool,
    volume_db: float = 0.0,
    logo_max_side: int = 120,
    frame_style: str = "blur",
    blur_sigma: float = 26.0,
    logo_anchor: str = "tr",
    logo_fps: float = 25.0,
    crf: int = 23,
    preset: str = "medium",
    audio_bitrate: str = "192k",
) -> list[str]:
    ffmpeg = ffmpeg_on_path()
    if not ffmpeg:
        raise ToolNotFoundError("ffmpeg not found on PATH.")
    with_logo = logo_path is not None
    fc, stream_maps = build_filter_complex(
        scale_w=scale_w,
        scale_h=scale_h,
        speed=speed,
        overlay_x=overlay_x,
        overlay_y=overlay_y,
        has_audio=has_audio,
        volume_db=volume_db,
        logo_max_side=logo_max_side,
        frame_style=frame_style,
        blur_sigma=blur_sigma,
        logo_anchor=logo_anchor,
        with_logo=with_logo,
    )
    cmd: list[str] = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        os.path.abspath(input_path),
    ]
    if with_logo:
        cmd.extend(
            [
                "-loop",
                "1",
                "-framerate",
                str(logo_fps),
                "-i",
                os.path.abspath(logo_path),
            ]
        )
    cmd.extend(
        [
            "-filter_complex",
            fc,
            *stream_maps,
            "-shortest",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
        ]
    )
    if has_audio:
        cmd.extend(["-c:a", "aac", "-b:a", audio_bitrate])
    else:
        cmd.extend(["-an"])
    cmd.append(os.path.abspath(output_path))
    return cmd


def run_ffmpeg(
    cmd: list[str],
    *,
    verbose: bool = False,
) -> subprocess.CompletedProcess[str]:
    logger.debug("Running: %s", " ".join(cmd))
    if verbose:
        return subprocess.run(cmd, check=False, text=True)
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        merged = "\n".join(
            part for part in ((proc.stderr or "").strip(), (proc.stdout or "").strip()) if part
        )
        if merged:
            logger.debug("%s", merged)
    return proc
