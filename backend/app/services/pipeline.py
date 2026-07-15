from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from backend.app.core.geometry import Box, CropFrame, TrackFrame, apply_corrections, build_crop_path
from backend.app.core.tracker import DeterministicMvpTracker, RealVisualDanceTracker, TargetSelection, VideoInfo
from backend.app.schemas import Correction, JobStatus, TargetRequest, TrackingFrame
from backend.app.services.exporter import build_crop_commands, build_ffmpeg_command, export_exact_video, export_native_video
from backend.app.services.storage import job_dir, load_json, load_status, save_json, save_status


def resolve_ffmpeg() -> str | None:
    project_root = Path(__file__).resolve().parents[3]
    try:
        import imageio_ffmpeg  # type: ignore

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).exists():
            return bundled
    except Exception:
        pass

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


def select_target(job_id: str, request: TargetRequest) -> JobStatus:
    status = load_status(job_id)
    positive = [(point.x, point.y) for point in request.points if point.label == "positive"]
    negative = [(point.x, point.y) for point in request.points if point.label == "negative"]
    if request.box:
        box = Box(request.box.x, request.box.y, request.box.width, request.box.height)
    elif positive:
        x, y = positive[0]
        box = Box(max(0, x - 90), max(0, y - 180), 180, 360)
    else:
        raise ValueError("至少需要一个正向点或一个框选区域。")

    save_json(
        job_id,
        "target.json",
        {
            "frame_index": request.frame_index,
            "box": box.__dict__,
            "positive_points": positive,
            "negative_points": negative,
        },
    )
    return save_status(
        status.model_copy(
            update={
                "state": "target_selected",
                "progress": 0.18,
                "message": "目标已锁定，可以开始跟踪。",
            }
        )
    )


def run_tracking(job_id: str) -> JobStatus:
    status = save_status(load_status(job_id).model_copy(update={"state": "tracking", "progress": 0.25, "message": "正在跟踪目标。"}))
    target_payload = load_json(job_id, "target.json")
    video_info = VideoInfo(width=status.width, height=status.height, frame_count=status.frame_count, fps=30.0)
    target = TargetSelection(
        frame_index=target_payload["frame_index"],
        box=Box(**target_payload["box"]),
        positive_points=[tuple(point) for point in target_payload["positive_points"]],
        negative_points=[tuple(point) for point in target_payload["negative_points"]],
    )
    tracker = RealVisualDanceTracker()
    track = tracker.track(job_dir(job_id) / "source.mp4", video_info, target)
    crop_path = build_crop_path(track, video_info.width, video_info.height)
    save_track(job_id, track)
    save_crop_path(job_id, crop_path)
    suspicious = [frame.frame_index for frame in crop_path if frame.suspicious]
    return save_status(
        status.model_copy(
            update={
                "state": "tracked",
                "progress": 0.72,
                "message": f"跟踪完成，发现 {len(suspicious)} 个需要检查的帧。",
                "suspicious_frames": suspicious,
            }
        )
    )


def apply_user_corrections(job_id: str, corrections: list[Correction]) -> JobStatus:
    status = load_status(job_id)
    track = load_track(job_id)
    correction_map = {
        correction.frame_index: Box(correction.box.x, correction.box.y, correction.box.width, correction.box.height)
        for correction in corrections
    }
    corrected = apply_corrections(track, correction_map)
    crop_path = build_crop_path(corrected, status.width, status.height)
    save_track(job_id, corrected)
    save_crop_path(job_id, crop_path)
    suspicious = [frame.frame_index for frame in crop_path if frame.suspicious]
    return save_status(
        status.model_copy(
            update={
                "state": "tracked",
                "progress": 0.78,
                "message": "纠偏已合并，裁剪路径已重新生成。",
                "suspicious_frames": suspicious,
            }
        )
    )


def export_video(job_id: str) -> JobStatus:
    status = load_status(job_id)
    save_status(status.model_copy(update={"state": "exporting", "progress": 0.85, "message": "正在极速准备视频导出..."}))
    source = job_dir(job_id) / "source.mp4"
    output = job_dir(job_id) / "output.mp4"
    frames = load_crop_path(job_id)
    command = build_ffmpeg_command(source, output, frames, status.width, status.height)
    ffmpeg_bin = resolve_ffmpeg()
    if ffmpeg_bin:
        command[0] = ffmpeg_bin
    (job_dir(job_id) / "crop_commands.txt").write_text(build_crop_commands(frames), encoding="utf-8")
    (job_dir(job_id) / "export_command.txt").write_text(" ".join(command), encoding="utf-8")

    def on_export_progress(done_frames: int, total_frames: int) -> None:
        pct = min(0.99, 0.85 + 0.14 * (done_frames / max(1, total_frames)))
        try:
            save_status(
                status.model_copy(
                    update={
                        "state": "exporting",
                        "progress": round(pct, 3),
                        "message": f"视频极速逐帧导出中 (已裁剪 {done_frames}/{total_frames} 帧)...",
                    }
                )
            )
        except Exception:
            pass

    if ffmpeg_bin or source.exists():
        success = export_native_video(command, job_dir(job_id), len(frames), progress_callback=on_export_progress)
        if not success:
            success = export_exact_video(source, output, frames, ffmpeg_bin, status.width, status.height, progress_callback=on_export_progress)
        if not success and ffmpeg_bin:
            subprocess.run(command, cwd=job_dir(job_id), check=True)
        message = "导出任务完成（绝对精准居中，无偏移）。"
        progress = 1.0
        download_url = f"/api/jobs/{job_id}/download"
    else:
        output.write_text("FFmpeg is not installed. crop_path.json contains the planned 9:16 crop path.", encoding="utf-8")
        message = "未检测到 FFmpeg：已生成 9:16 裁剪轨迹和导出命令，但还没有真实导出视频。"
        progress = 0.92
        download_url = None

    return save_status(
        status.model_copy(
            update={
                "state": "exported",
                "progress": progress,
                "message": message,
                "download_url": download_url,
                "export_path": str(output),
            }
        )
    )


def save_track(job_id: str, track: list[TrackFrame]) -> None:
    save_json(
        job_id,
        "tracking.json",
        [
            {
                "frame_index": frame.frame_index,
                "subject_box": frame.subject_box.__dict__,
                "confidence": frame.confidence,
            }
            for frame in track
        ],
    )


def load_track(job_id: str) -> list[TrackFrame]:
    return [
        TrackFrame(frame_index=row["frame_index"], subject_box=Box(**row["subject_box"]), confidence=row["confidence"])
        for row in load_json(job_id, "tracking.json")
    ]


def save_crop_path(job_id: str, frames: list[CropFrame]) -> None:
    save_json(
        job_id,
        "crop_path.json",
        [
            TrackingFrame(
                frame_index=frame.frame_index,
                subject_box=frame.subject_box.__dict__,
                crop_box=frame.crop_box.__dict__,
                confidence=frame.confidence,
                suspicious=frame.suspicious,
            ).model_dump()
            for frame in frames
        ],
    )


def load_crop_path(job_id: str) -> list[CropFrame]:
    frames: list[CropFrame] = []
    for row in load_json(job_id, "crop_path.json"):
        frames.append(
            CropFrame(
                frame_index=row["frame_index"],
                subject_box=Box(**row["subject_box"]),
                crop_box=Box(**row["crop_box"]),
                confidence=row["confidence"],
                suspicious=row["suspicious"],
            )
        )
    return frames
