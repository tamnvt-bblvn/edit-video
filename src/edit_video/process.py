from __future__ import annotations

import logging
import math
import os
import sys
from dataclasses import dataclass

from edit_video.ffmpeg import (
    build_ffmpeg_command,
    ensure_tools,
    probe_has_audio,
    run_ffmpeg,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessVideoResult:
    returncode: int
    had_audio: bool


def process_video(
    input_path: str,
    output_path: str,
    logo_path: str,
    scale_w: int,
    scale_h: int,
    speed: float,
    *,
    overlay_x: int = 12,
    overlay_y: int = 12,
    logo_fps: float = 25.0,
    crf: int = 23,
    preset: str = "medium",
    audio_bitrate: str = "192k",
    volume_db: float = 0.0,
    logo_max_side: int = 120,
    frame_style: str = "blur",
    blur_sigma: float = 26.0,
    logo_anchor: str = "tr",
    quiet: bool = False,
    verbose: bool = False,
    job_ctx: str | None = None,
) -> ProcessVideoResult:
    """
    Scale main video, change playback speed, overlay a logo, re-encode to H.264/AAC.

    Requires ``ffmpeg`` and ``ffprobe`` on PATH.

    Configure the standard library :mod:`logging` to control messages (the CLI sets
    When ``quiet`` is true, INFO-level messages are skipped.
    If ``job_ctx`` is set (e.g. ``a1b2c3d4:2/5``), concise progress lines are still
    logged at INFO for that encode, which helps trace batch or API jobs.
    """
    if speed <= 0:
        raise ValueError("speed must be positive")
    if scale_w <= 0 or scale_h <= 0:
        raise ValueError("width and height must be positive")
    if logo_fps <= 0:
        raise ValueError("logo_fps must be positive")
    if not 0 <= crf <= 51:
        raise ValueError("crf must be between 0 and 51")
    if not math.isfinite(volume_db):
        raise ValueError("volume_db must be a finite number")
    if not -96.0 <= volume_db <= 24.0:
        raise ValueError("volume_db must be between -96 and 24 (decibels)")
    if logo_max_side < 0 or logo_max_side > 4096:
        raise ValueError("logo_max_side must be between 0 and 4096 (0 = keep native logo pixels)")
    fs = frame_style.strip().lower()
    if fs not in ("blur", "pad", "stretch"):
        raise ValueError("frame_style must be 'blur', 'pad', or 'stretch'")
    la = logo_anchor.strip().lower()
    if la not in ("tl", "tr", "bl", "br"):
        raise ValueError("logo_anchor must be tl, tr, bl, or br")
    if blur_sigma < 0.5 or blur_sigma > 100.0:
        raise ValueError("blur_sigma must be between 0.5 and 100")

    for label, p in (
        ("input", input_path),
        ("logo", logo_path),
    ):
        if not os.path.isfile(p):
            raise FileNotFoundError(f"{label} file not found: {p}")

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.isdir(out_dir):
        raise FileNotFoundError(f"output directory does not exist: {out_dir}")

    ensure_tools()
    has_audio = probe_has_audio(input_path)

    _in_base = os.path.basename(input_path)
    _out_base = os.path.basename(output_path)
    if job_ctx:
        logger.info(
            "[%s] Chuẩn bị FFmpeg | %s → %s | %dx%d speed=%s preset=%s style=%s | có_audio=%s",
            job_ctx,
            _in_base,
            _out_base,
            scale_w,
            scale_h,
            speed,
            preset,
            frame_style,
            has_audio,
        )
    elif not has_audio and not quiet:
        logger.info("No audio stream detected; output will be video-only.")

    cmd = build_ffmpeg_command(
        input_path=input_path,
        output_path=output_path,
        logo_path=logo_path,
        scale_w=scale_w,
        scale_h=scale_h,
        speed=speed,
        overlay_x=overlay_x,
        overlay_y=overlay_y,
        has_audio=has_audio,
        logo_fps=logo_fps,
        crf=crf,
        preset=preset,
        audio_bitrate=audio_bitrate,
        volume_db=volume_db,
        logo_max_side=logo_max_side,
        frame_style=frame_style,
        blur_sigma=blur_sigma,
        logo_anchor=logo_anchor,
    )
    proc = run_ffmpeg(cmd, verbose=verbose)
    rc = proc.returncode
    out_path = os.path.abspath(output_path)

    if rc == 0:
        if job_ctx:
            logger.info("[%s] FFmpeg xong (exit 0) → %s", job_ctx, out_path)
        elif not quiet:
            logger.info("Wrote %s", out_path)
    else:
        stderr = ""
        stdout = ""
        if not verbose and proc.stderr is not None:
            stderr = proc.stderr.strip()
        if not verbose and proc.stdout is not None:
            stdout = proc.stdout.strip()
        detail = "\n".join(part for part in (stderr, stdout) if part)
        if job_ctx:
            if detail:
                logger.error("[%s] FFmpeg lỗi (exit %d):\n%s", job_ctx, rc, detail)
            else:
                logger.error("[%s] FFmpeg lỗi (exit %d)", job_ctx, rc)
        elif quiet:
            if detail:
                print(detail, file=sys.stderr, flush=True)
            else:
                print(f"ffmpeg exited with status {rc}", file=sys.stderr, flush=True)
        elif detail:
            logger.error("ffmpeg failed (exit %d):\n%s", rc, detail)
        else:
            logger.error("ffmpeg exited with status %d", rc)

    return ProcessVideoResult(returncode=rc, had_audio=has_audio)
