from __future__ import annotations

import logging
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from edit_video._version import package_version
from edit_video.exceptions import EditVideoError
from edit_video.logo_scale import resolve_logo_max_side_for_frame
from edit_video.process import process_video
from edit_video.web.config import (
    batch_encode_workers,
    ffmpeg_verbose_from_env,
    max_batch_videos,
    max_upload_bytes,
)
from edit_video.web.io_util import (
    allowed_suffix,
    logo_extensions,
    safe_download_stem,
    stream_upload_to_path,
    unique_edited_mp4_arcname,
    video_extensions,
)

logger = logging.getLogger(__name__)


def _threading_snapshot() -> str:
    cur = threading.current_thread()
    return (
        f"active_threads={threading.active_count()} "
        f"current_thread={cur.name!r} daemon={cur.daemon}"
    )


_X264_PRESETS = frozenset(
    {
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
        "medium",
        "slow",
        "slower",
        "veryslow",
    },
)

_DEFAULT_X264_PRESET = "medium"


def create_app() -> FastAPI:
    app = FastAPI(
        title="edit-video",
        description="Scale, chỉnh tốc độ và ghép logo lên video (FFmpeg)",
        version=package_version(),
    )

    base = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(base / "templates"))

    static_dir = base / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/", include_in_schema=False)
    async def index(request: Request):
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "max_upload_mb": max_upload_bytes() // (1024 * 1024),
                "max_batch_videos": max_batch_videos(),
                "preset_options": [
                    {"value": p, "selected": p == _DEFAULT_X264_PRESET}
                    for p in sorted(_X264_PRESETS)
                ],
            },
        )

    @app.post("/api/process")
    async def api_process(
        videos: Annotated[
            list[UploadFile],
            File(description="Một hoặc nhiều video — cùng logo và cùng thông số"),
        ],
        logo: Annotated[
            UploadFile | None,
            File(description="Ảnh / icon làm watermark (tuỳ chọn)"),
        ] = None,
        width: int = Form(..., ge=16, le=7680, description="Chiều rộng đầu ra"),
        height: int = Form(..., ge=16, le=4320, description="Chiều cao đầu ra"),
        speed: float = Form(..., gt=0, le=64, description="Hệ số tốc độ (2 = nhanh gấp đôi)"),
        overlay_x: int = Form(12, ge=0, le=8192),
        overlay_y: int = Form(12, ge=0, le=8192),
        logo_max_side: int = Form(
            120,
            ge=0,
            le=4096,
            description="Kích thước tối đa cạnh logo (px) khi logo_max_side_pct = 0",
        ),
        logo_max_side_pct: float = Form(
            0.0,
            ge=0.0,
            le=50.0,
            description=(
                ">0: scale logo theo % max(chieu_rong,chieu_cao) khung ra; "
                "0 = dùng logo_max_side"
            ),
        ),
        frame_style: str = Form(
            "blur",
            description="blur | pad | stretch (kéo giãn đủ WxH, có thể méo tỉ lệ)",
        ),
        blur_sigma: float = Form(26.0, ge=0.5, le=100.0, description="Sigma Gaussian cho nền blur"),
        logo_anchor: str = Form(
            "tr",
            description="tl | tr | bl | br — neo logo",
        ),
        logo_fps: float = Form(25.0, gt=0, le=120),
        crf: int = Form(23, ge=0, le=51),
        preset: str = Form(_DEFAULT_X264_PRESET),
        audio_bitrate: str = Form("192k"),
        volume_db: float = Form(
            0.0,
            ge=-96.0,
            le=24.0,
            description="Điều chỉnh âm lượng (dB): âm = nhỏ hơn, dương = to hơn",
        ),
    ) -> FileResponse:
        preset_norm = preset.strip().lower()
        if preset_norm not in _X264_PRESETS:
            raise HTTPException(
                status_code=400,
                detail=f"preset không hợp lệ: {preset}. Chọn một trong: "
                + ", ".join(sorted(_X264_PRESETS)),
            )

        fs = frame_style.strip().lower()
        if fs not in ("blur", "pad", "stretch"):
            raise HTTPException(
                status_code=400,
                detail="frame_style phải là blur, pad hoặc stretch.",
            )
        la = logo_anchor.strip().lower()
        if la not in ("tl", "tr", "bl", "br"):
            raise HTTPException(status_code=400, detail="logo_anchor phải là tl, tr, bl hoặc br.")

        if not videos:
            raise HTTPException(status_code=400, detail="Cần ít nhất một file video.")

        batch_limit = max_batch_videos()
        if len(videos) > batch_limit:
            raise HTTPException(
                status_code=400,
                detail=f"Tối đa {batch_limit} video mỗi lần (hoặc chỉnh EDIT_VIDEO_MAX_BATCH).",
            )

        req_id = uuid.uuid4().hex[:8]
        workers_cap = batch_encode_workers()
        logger.info(
            "[%s] POST /api/process | videos=%d blur_sigma=%s logo_anchor=%s workers_cap=%d | "
            "WxH=%dx%d speed=%s preset=%s frame_style=%s crf=%s vol_db=%s | %s",
            req_id,
            len(videos),
            blur_sigma,
            la,
            workers_cap,
            width,
            height,
            speed,
            preset_norm,
            fs,
            crf,
            volume_db,
            _threading_snapshot(),
        )

        ffmpeg_verbose = ffmpeg_verbose_from_env()
        if ffmpeg_verbose:
            logger.warning(
                "[%s] EDIT_VIDEO_FFMPEG_VERBOSE=bật → ffmpeg ghi trực tiếp stderr (nhiễu log có thể xen kẽ)",
                req_id,
            )

        try:
            if logo is not None and logo.filename:
                logo_px = resolve_logo_max_side_for_frame(
                    frame_w=width,
                    frame_h=height,
                    logo_max_side=logo_max_side,
                    logo_max_side_pct=logo_max_side_pct,
                )
            else:
                logo_px = 0
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        if logo is not None and logo.filename:
            lsuffix = allowed_suffix(logo, logo_extensions())
        else:
            lsuffix = None
        bound = max_upload_bytes()

        work = Path(tempfile.mkdtemp(prefix="edit_video_"))
        logo_path: Path | None = None
        video_entries: list[tuple[str, Path]] = []

        try:
            if logo is not None and logo.filename:
                logo_path = work / f"logo{lsuffix}"
                await stream_upload_to_path(logo, logo_path, max_bytes=bound)
            for i, uf in enumerate(videos):
                suf = allowed_suffix(uf, video_extensions())
                dest = work / f"in_{i}{suf}"
                await stream_upload_to_path(uf, dest, max_bytes=bound)
                disp = uf.filename or f"video_{i}{suf}"
                video_entries.append((disp, dest))
        except HTTPException:
            shutil.rmtree(work, ignore_errors=True)
            raise
        except Exception:
            shutil.rmtree(work, ignore_errors=True)
            logger.exception("Lỗi lưu upload")
            raise HTTPException(status_code=500, detail="Không thể lưu file tạm.") from None

        logger.info(
            "[%s] Upload xong → thư_mục_tạm=%s | %s",
            req_id,
            work.name,
            _threading_snapshot(),
        )

        ab_br = audio_bitrate.strip() or "192k"

        def _call_process(inp: Path, outp: Path, *, job_ctx: str) -> int:
            r = process_video(
                str(inp),
                str(outp),
                str(logo_path) if logo_path is not None else None,
                width,
                height,
                speed,
                overlay_x=overlay_x,
                overlay_y=overlay_y,
                logo_max_side=logo_px,
                frame_style=fs,
                blur_sigma=blur_sigma,
                logo_anchor=la,
                logo_fps=logo_fps,
                crf=crf,
                preset=preset_norm,
                audio_bitrate=ab_br,
                volume_db=volume_db,
                quiet=True,
                verbose=ffmpeg_verbose,
                job_ctx=job_ctx,
            )
            return r.returncode

        if len(video_entries) == 1:
            disp0, video_path = video_entries[0]
            out_path = work / "output.mp4"

            def _job_single() -> int:
                return _call_process(video_path, out_path, job_ctx=f"{req_id}:1/1")

            logger.info("[%s] Encode 1 video | %s", req_id, _threading_snapshot())
            t_enc = time.perf_counter()
            try:
                code = await run_in_threadpool(_job_single)
            except (EditVideoError, OSError, ValueError) as e:
                shutil.rmtree(work, ignore_errors=True)
                logger.warning("process_video refused: %s", e)
                raise HTTPException(status_code=400, detail=str(e)) from e
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                logger.exception("process_video crashed")
                raise HTTPException(status_code=500, detail="Lỗi xử lý video.") from None

            logger.info(
                "[%s] Encode 1 video xong trong %.2fs | exit=%d | %s",
                req_id,
                time.perf_counter() - t_enc,
                code,
                _threading_snapshot(),
            )

            if code != 0 or not out_path.is_file():
                shutil.rmtree(work, ignore_errors=True)
                raise HTTPException(
                    status_code=422,
                    detail="FFmpeg không tạo được file đầu ra. Kiểm tra format video/audio.",
                )

            download = f"{safe_download_stem(disp0)}_edited.mp4"

            def _cleanup_single() -> None:
                shutil.rmtree(work, ignore_errors=True)

            return FileResponse(
                path=str(out_path),
                filename=download,
                media_type="video/mp4",
                background=BackgroundTask(_cleanup_single),
            )

        def _batch_job() -> tuple[list[tuple[str, Path]], list[tuple[str, str]]]:
            _Row = tuple[int, str, Path | None, str | None]

            n_v = len(video_entries)
            workers = min(batch_encode_workers(), n_v)
            done_lock = threading.Lock()
            done_count = 0

            def _one(idx: int, disp_name: str, vpath: Path) -> _Row:
                nonlocal done_count
                job_label = f"{req_id}:{idx + 1}/{n_v}"
                outp = work / f"out_{idx}.mp4"
                logger.info(
                    "[%s] Batch job start | file=%s | thread=%s | pool_workers=%d | %s",
                    job_label,
                    disp_name,
                    threading.current_thread().name,
                    workers,
                    _threading_snapshot(),
                )
                row: _Row
                try:
                    code = _call_process(vpath, outp, job_ctx=job_label)
                    if code != 0 or not outp.is_file():
                        row = (idx, disp_name, None, "FFmpeg không tạo được file đầu ra.")
                    else:
                        row = (idx, disp_name, outp, None)
                except (EditVideoError, OSError, ValueError) as e:
                    row = (idx, disp_name, None, str(e))
                except Exception:
                    logger.exception("Lỗi xử lý file trong batch: %s", disp_name)
                    row = (idx, disp_name, None, "Lỗi không xác định khi encode.")
                with done_lock:
                    done_count += 1
                    logger.info(
                        "[%s] Batch job end | tiến_độ=%d/%d | %s",
                        job_label,
                        done_count,
                        n_v,
                        _threading_snapshot(),
                    )
                return row

            rows: list[_Row] = []
            logger.info(
                "[%s] Mở ThreadPoolExecutor max_workers=%d (≤ workers_cap=%d, n_videos=%d) | %s",
                req_id,
                workers,
                batch_encode_workers(),
                n_v,
                _threading_snapshot(),
            )
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_one, i, disp_name, vpath)
                    for i, (disp_name, vpath) in enumerate(video_entries)
                ]
                for fut in as_completed(futures):
                    rows.append(fut.result())

            rows.sort(key=lambda r: r[0])
            successes: list[tuple[str, Path]] = []
            failures: list[tuple[str, str]] = []
            used_arc: set[str] = set()
            for _idx, disp_name, outp, err in rows:
                if err is not None:
                    failures.append((disp_name, err))
                    continue
                assert outp is not None
                arc = unique_edited_mp4_arcname(disp_name, used_arc)
                successes.append((arc, outp))
            return successes, failures

        try:
            t_batch = time.perf_counter()
            successes, failures = await run_in_threadpool(_batch_job)
            logger.info(
                "[%s] Batch FFmpeg pool hoàn tất trong %.2fs | ok=%d fail=%d | %s",
                req_id,
                time.perf_counter() - t_batch,
                len(successes),
                len(failures),
                _threading_snapshot(),
            )
        except Exception:
            shutil.rmtree(work, ignore_errors=True)
            logger.exception("batch encode crashed")
            raise HTTPException(status_code=500, detail="Lỗi xử lý hàng loạt.") from None

        if not successes:
            shutil.rmtree(work, ignore_errors=True)
            detail: list[dict[str, str]] = [{"file": fn, "error": err} for fn, err in failures]
            raise HTTPException(
                status_code=422,
                detail=detail if detail else "Không encode được video nào.",
            )

        zip_path = work / "batch_edited.zip"
        logger.info("[%s] Đang tạo ZIP đầu ra… | %s", req_id, _threading_snapshot())
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for arc, pth in successes:
                    zf.write(pth, arcname=arc)
                if failures:
                    body_lines = [f"{fn}\t{err}" for fn, err in failures]
                    zf.writestr(
                        "_batch_errors.txt",
                        "Các file sau không encode được:\n\n" + "\n".join(body_lines) + "\n",
                        compress_type=zipfile.ZIP_DEFLATED,
                    )
            logger.info("[%s] ZIP sẵn sàng → %s | %s", req_id, zip_path.name, _threading_snapshot())
        except OSError:
            shutil.rmtree(work, ignore_errors=True)
            logger.exception("Không tạo được ZIP")
            raise HTTPException(status_code=500, detail="Không tạo được file ZIP.") from None

        def _cleanup_batch() -> None:
            shutil.rmtree(work, ignore_errors=True)

        return FileResponse(
            path=str(zip_path),
            filename="edited_batch.zip",
            media_type="application/zip",
            background=BackgroundTask(_cleanup_batch),
        )

    return app


app = create_app()
