from __future__ import annotations

import argparse
import logging
import sys

from edit_video._version import package_version
from edit_video.exceptions import EditVideoError
from edit_video.logo_scale import resolve_logo_max_side_for_frame
from edit_video.process import process_video


def _configure_logging(*, verbose: bool, quiet: bool) -> None:
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )


def build_parser() -> argparse.ArgumentParser:
    ver = package_version()
    parser = argparse.ArgumentParser(
        prog="edit_video",
        description="Scale video, adjust speed, overlay a logo image (FFmpeg).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "Example: edit_video -i in.mp4 -o out.mp4 -l logo.png "
            "--width 1280 --height 720 --speed 2"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {ver}",
        help="Show version and exit",
    )
    parser.add_argument("--input", "-i", required=True, help="Input video path")
    parser.add_argument("--output", "-o", required=True, help="Output video path")
    parser.add_argument(
        "--logo",
        "-l",
        default=None,
        help="Logo image (e.g. PNG); bỏ qua nếu không cần watermark",
    )
    parser.add_argument("--width", type=int, required=True, help="Output width (pixels)")
    parser.add_argument("--height", type=int, required=True, help="Output height (pixels)")
    parser.add_argument(
        "--speed",
        type=float,
        required=True,
        help="Playback speed factor (e.g. 2.0 = 2x faster)",
    )
    parser.add_argument(
        "--overlay-x",
        type=int,
        default=12,
        help="Lề logo theo trục ngang (trái hoặc phải tuỳ --logo-anchor)",
    )
    parser.add_argument(
        "--overlay-y",
        type=int,
        default=12,
        help="Lề logo theo trục dọc (trên hoặc dưới tuỳ --logo-anchor)",
    )
    parser.add_argument(
        "--logo-fps",
        type=float,
        default=25.0,
        help="Framerate for looped still logo input",
    )
    parser.add_argument("--crf", type=int, default=23, help="libx264 CRF (0–51)")
    parser.add_argument(
        "--preset",
        default="medium",
        help="libx264 preset (ultrafast…veryslow)",
    )
    parser.add_argument(
        "--audio-bitrate",
        default="192k",
        help="AAC bitrate",
    )
    parser.add_argument(
        "--logo-max-side",
        type=int,
        default=120,
        metavar="PX",
        help=(
            "Thu nhỏ logo vừa trong ô PX×PX (giữ tỷ lệ). 0 = giữ kích thước pixel ảnh gốc. "
            "Bị bỏ qua nếu --logo-max-side-pct > 0."
        ),
    )
    parser.add_argument(
        "--logo-max-side-pct",
        type=float,
        default=0.0,
        metavar="PCT",
        help=(
            "Nếu > 0: scale logo theo %% max(chieu_rong,chieu_cao) đầu ra; "
            "không phụ thuộc px ảnh gốc. 0 = dùng --logo-max-side."
        ),
    )
    parser.add_argument(
        "--frame-style",
        choices=("blur", "pad", "stretch"),
        default="blur",
        help=(
            "blur = nền mờ reel; pad = viền đen; "
            "stretch = kéo giãn đủ khung (méo nếu khác tỉ lệ)"
        ),
    )
    parser.add_argument(
        "--blur-sigma",
        type=float,
        default=26.0,
        metavar="SIGMA",
        help="Độ mờ Gaussian cho nền (chỉ khi --frame-style blur)",
    )
    parser.add_argument(
        "--logo-anchor",
        choices=("tl", "tr", "bl", "br"),
        default="tr",
        help="Góc neo logo: tl/tr/bl/br (tr = trên-phải như watermark reel)",
    )
    parser.add_argument(
        "--volume-db",
        type=float,
        default=0.0,
        metavar="DB",
        help="Gain âm thanh tương đối (dB). 0 = giữ nguyên; ví dụ -6 nhỏ hơn một nửa, +6 to hơn.",
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Only errors to logging; still prints a one-line failure if ffmpeg fails",
    )
    g.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging and stream ffmpeg output (no capture)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(verbose=args.verbose, quiet=args.quiet)

    try:
        if args.logo is not None:
            logo_px = resolve_logo_max_side_for_frame(
                frame_w=args.width,
                frame_h=args.height,
                logo_max_side=args.logo_max_side,
                logo_max_side_pct=args.logo_max_side_pct,
            )
        else:
            logo_px = 0
        res = process_video(
            input_path=args.input,
            output_path=args.output,
            logo_path=args.logo,
            scale_w=args.width,
            scale_h=args.height,
            speed=args.speed,
            overlay_x=args.overlay_x,
            overlay_y=args.overlay_y,
            logo_fps=args.logo_fps,
            crf=args.crf,
            preset=args.preset,
            audio_bitrate=args.audio_bitrate,
            volume_db=args.volume_db,
            logo_max_side=logo_px,
            frame_style=args.frame_style,
            blur_sigma=args.blur_sigma,
            logo_anchor=args.logo_anchor,
            quiet=args.quiet,
            verbose=args.verbose,
        )
    except (EditVideoError, OSError, ValueError) as e:
        logging.getLogger(__name__).error("%s", e)
        return 1

    return 0 if res.returncode == 0 else res.returncode


if __name__ == "__main__":
    raise SystemExit(main())
