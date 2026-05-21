# edit-video

CLI và giao diện web nhẹ (Python): scale video, đổi tốc độ phát, ghép logo bằng **FFmpeg** / **ffprobe**.

## Yêu cầu

- Python ≥ 3.10
- [FFmpeg](https://ffmpeg.org/) có trên `PATH` (kèm `ffprobe`)

## Cài đặt (venv)

```powershell
cd edit-video
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Thêm tuỳ chọn **web**:

```powershell
python -m pip install -e ".[dev,web]"
```

## Dùng nhanh (CLI)

```powershell
edit_video -i in.mp4 -o out.mp4 -l logo.png --width 1920 --height 1080 --speed 1 --logo-max-side 120 --frame-style blur --logo-anchor tr
python -m edit_video --help
python -m edit_video --version
```

## Giao diện web

```powershell
edit_video_web
```

Mở trình duyệt trên máy chạy server: `http://127.0.0.1:8000/` — hoặc từ máy khác trong LAN: `http://<IP-máy-chạy>:8000/`
(mặc định server lắng nghe **mọi giao diện mạng** `0.0.0.0`; chỉ localhost thì đặt `EDIT_VIDEO_HOST=127.0.0.1`). Mặc định **1080p**, **nền blur** hai bên (video dọc ở giữa giống reel), logo
**trên-phải**. **Một file** → MP4; **nhiều file** → ZIP. API gửi field **`videos`** (lặp cho nhiều file). Xem form cho
`frame_style` (`blur` · `pad` · `stretch` — kéo giãn đủ khung), `logo_anchor`, `blur_sigma`. **Logo:** đặt `% cạnh dài khung` (max chiều ngang/dọc đầu ra; form mặc định 12%) để tự scale; hoán **1080×1920 ↔ 1920×1080** vẫn cùng cỡ watermark; `0` → dùng px cố định.

Biến môi trường (tuỳ chọn):

- `EDIT_VIDEO_HOST` (mặc định `0.0.0.0` — cho phép truy cập LAN; dùng `127.0.0.1` nếu chỉ mở trên máy local)
- `EDIT_VIDEO_PORT` (mặc định `8000`)
- `EDIT_VIDEO_MAX_UPLOAD_MB` (mặc định `500`) — trên mỗi file (video hoặc logo)
- `EDIT_VIDEO_MAX_BATCH` (mặc định `25`) — số video tối đa mỗi request batch
- `EDIT_VIDEO_BATCH_WORKERS` (tuỳ chọn; mặc định `min(4, số CPU)`) — số FFmpeg chạy **song song** trong một batch (tối đa 32). Tăng có thể nhanh hơn nhưng tốn CPU/RAM.
- `EDIT_VIDEO_RELOAD` — mặc định **bật** (uvicorn reload khi đổi mã trong `edit_video`). Đặt `0`, `false` hoặc `no` để
  tắt (production).

Chạy bằng module:

```powershell
python -m edit_video.web
# hoặc
python -m edit_video.web.server
```

Hoặc: `python -m uvicorn edit_video.web.app:app --host 0.0.0.0 --port 8000`

## Kiểm thử & lint

```powershell
ruff check src tests
ruff format --check src tests
pytest -q
```

## Thư viện

```python
from edit_video import process_video

process_video(
    "in.mp4", "out.mp4", "logo.png",
    scale_w=1920, scale_h=1080, speed=1.0,
    logo_max_side=120,
    frame_style="blur",
    blur_sigma=26.0,
    logo_anchor="tr",
    overlay_x=12,
    overlay_y=12,
)
```

Với API nhúng ứng dụng, cấu hình `logging` chuẩn thư viện để điều chỉnh mức log.
