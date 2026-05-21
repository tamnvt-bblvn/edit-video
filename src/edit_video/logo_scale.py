"""Derive FFmpeg logo scale from output frame size."""

from __future__ import annotations

import math


def resolve_logo_max_side_for_frame(
    *,
    frame_w: int,
    frame_h: int,
    logo_max_side: int,
    logo_max_side_pct: float,
) -> int:
    """
    Effective ``logo_max_side`` for :func:`~edit_video.process.process_video`.

    If ``logo_max_side_pct`` > 0, the logo's longest side targets ``pct%`` of
    ``max(frame_w, frame_h)``. Using the **long** side makes **1080×1920** and
    **1920×1080** produce the **same** logo pixel size (both have max 1920), so
    swapping portrait/landscape output no longer changes watermark scale.

    Otherwise returns ``logo_max_side`` unchanged (including ``0`` = native pixels).
    """
    if not math.isfinite(logo_max_side_pct):
        raise ValueError("logo_max_side_pct must be a finite number")
    if logo_max_side_pct < 0 or logo_max_side_pct > 50:
        raise ValueError("logo_max_side_pct must be between 0 and 50")
    if logo_max_side_pct > 0:
        long = max(frame_w, frame_h)
        raw = long * (logo_max_side_pct / 100.0)
        m = int(round(raw))
        m = max(2, min(4096, m))
        m -= m % 2
        return max(m, 2)
    return logo_max_side
