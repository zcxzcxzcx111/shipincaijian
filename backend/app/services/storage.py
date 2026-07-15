from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from backend.app.schemas import JobStatus


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FRAME_COUNT = 300


def job_dir(job_id: str) -> Path:
    return DATA_DIR / job_id


def resolve_local_ffmpeg() -> str | None:
    project_root = Path(__file__).resolve().parents[3]
    candidates = [
        shutil.which("ffmpeg"),
        str((project_root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe")),
        str((project_root / "tools" / "ffmpeg" / "ffmpeg.exe")),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate

    node_modules = project_root / "node_modules"
    if node_modules.exists():
        for candidate in node_modules.glob(".pnpm/@ffmpeg-installer+win32-x64@*/node_modules/@ffmpeg-installer/win32-x64/ffmpeg.exe"):
            if candidate.exists():
                return str(candidate)
    return None


def probe_video(source_path: Path) -> tuple[int, int, int]:
    ffmpeg = resolve_local_ffmpeg()
    if not ffmpeg:
        return DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FRAME_COUNT

    try:
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(source_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
    except OSError:
        return DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FRAME_COUNT

    output = f"{completed.stdout}\n{completed.stderr}"
    video_line = next((line for line in output.splitlines() if "Video:" in line), "")
    size_match = re.search(r"(?<![x\d])(\d{2,5})x(\d{2,5})(?![x\d])", video_line)
    width = int(size_match.group(1)) if size_match else DEFAULT_WIDTH
    height = int(size_match.group(2)) if size_match else DEFAULT_HEIGHT

    duration_seconds = 0.0
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
    if duration_match:
        hours, minutes, seconds = duration_match.groups()
        duration_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    fps = 30.0
    fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", video_line)
    if fps_match:
        fps = float(fps_match.group(1))

    frame_count = round(duration_seconds * fps) if duration_seconds > 0 and fps > 0 else DEFAULT_FRAME_COUNT
    return width, height, max(1, frame_count)


def create_job_file(source_filename: str, file_obj: Any) -> JobStatus:
    job_id = uuid.uuid4().hex[:12]
    folder = job_dir(job_id)
    folder.mkdir(parents=True, exist_ok=False)
    source_path = folder / "source.mp4"
    with source_path.open("wb") as handle:
        shutil.copyfileobj(file_obj, handle)

    width, height, frame_count = probe_video(source_path)
    status = JobStatus(
        id=job_id,
        state="created",
        progress=0.05,
        message="任务已创建，等待选择目标人物。",
        source_filename=source_filename,
        proxy_url=None,
        download_url=None,
        export_path=None,
        suspicious_frames=[],
        frame_count=frame_count,
        width=width,
        height=height,
    )
    save_json(job_id, "status.json", status.model_dump())
    return status


def save_json(job_id: str, filename: str, payload: Any) -> None:
    folder = job_dir(job_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(job_id: str, filename: str) -> Any:
    return json.loads((job_dir(job_id) / filename).read_text(encoding="utf-8"))


def load_status(job_id: str) -> JobStatus:
    payload = load_json(job_id, "status.json")
    crop_path_file = job_dir(job_id) / "crop_path.json"
    if crop_path_file.exists():
        try:
            payload["tracking_frames"] = json.loads(crop_path_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return JobStatus(**payload)


def save_status(status: JobStatus) -> JobStatus:
    save_json(status.id, "status.json", status.model_dump(exclude={"tracking_frames"}))
    return status
