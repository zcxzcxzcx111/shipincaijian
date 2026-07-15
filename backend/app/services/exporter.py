from __future__ import annotations

import math
from pathlib import Path

from backend.app.core.geometry import CropFrame


def compute_padding(frames: list[CropFrame], frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
    left = math.ceil(max(0.0, max(-frame.crop_box.x for frame in frames)))
    top = math.ceil(max(0.0, max(-frame.crop_box.y for frame in frames)))
    right = math.ceil(max(0.0, max(frame.crop_box.x + frame.crop_box.width - frame_width for frame in frames)))
    bottom = math.ceil(max(0.0, max(frame.crop_box.y + frame.crop_box.height - frame_height for frame in frames)))
    return left, top, right, bottom


def build_filter_script(
    frames: list[CropFrame],
    frame_width: int = 1280,
    frame_height: int = 720,
    output_width: int = 1080,
    output_height: int = 1920,
) -> str:
    if not frames:
        raise ValueError("crop path is empty")
    first = frames[0].crop_box
    pad_left, pad_top, pad_right, pad_bottom = compute_padding(frames, frame_width, frame_height)
    filters: list[str] = []
    if pad_left or pad_top or pad_right or pad_bottom:
        filters.append(
            f"pad=w=iw+{pad_left + pad_right}:h=ih+{pad_top + pad_bottom}:x={pad_left}:y={pad_top}:color=black,"
        )
    commands = [
        "sendcmd=f=crop_commands.txt,"
        f"crop@focus=w={round(first.width)}:h={round(first.height)}:x={round(first.x + pad_left)}:y={round(first.y + pad_top)},"
        f"scale={output_width}:{output_height}"
    ]
    return "".join(filters + commands)


def build_crop_commands(frames: list[CropFrame], fps: float = 30.0) -> str:
    pad_left = math.ceil(max(0.0, max(-frame.crop_box.x for frame in frames)))
    pad_top = math.ceil(max(0.0, max(-frame.crop_box.y for frame in frames)))
    lines: list[str] = []
    for frame in frames:
        timestamp = frame.frame_index / fps
        crop = frame.crop_box
        lines.append(f"{timestamp:.6f} focus x {round(crop.x + pad_left)};")
        lines.append(f"{timestamp:.6f} focus y {round(crop.y + pad_top)};")
        lines.append(f"{timestamp:.6f} focus w {round(crop.width)};")
        lines.append(f"{timestamp:.6f} focus h {round(crop.height)};")
    return "\n".join(lines) + "\n"


def build_ffmpeg_command(source: Path, output: Path, frames: list[CropFrame], frame_width: int = 1280, frame_height: int = 720) -> list[str]:
    out_w, out_h = (1080, 1920) if frame_height >= 1080 or frame_width >= 1920 else (720, 1280)
    filter_script = build_filter_script(frames, frame_width, frame_height, out_w, out_h)
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vf",
        filter_script,
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "18",
        "-c:a",
        "copy",
        str(output),
    ]


def export_native_video(
    command: list[str],
    cwd: Path,
    total_frames: int,
    progress_callback: callable | None = None,
) -> bool:
    import subprocess
    import re

    try:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if proc.stderr:
            frame_pattern = re.compile(rb"frame=\s*(\d+)")
            buffer = b""
            while True:
                chunk = proc.stderr.read(256)
                if not chunk:
                    if proc.poll() is not None:
                        break
                    continue
                buffer += chunk
                parts = re.split(rb"[\r\n]+", buffer)
                if len(parts) > 1:
                    for part in parts[:-1]:
                        m = frame_pattern.search(part)
                        if m and progress_callback:
                            try:
                                done = int(m.group(1).decode("ascii"))
                                progress_callback(done, max(1, total_frames))
                            except Exception:
                                pass
                    buffer = parts[-1]
        proc.wait()
        return proc.returncode == 0
    except Exception:
        return False


def export_exact_video(
    source: Path,
    output: Path,
    frames: list[CropFrame],
    ffmpeg_bin: str | None = None,
    frame_width: int = 1280,
    frame_height: int = 720,
    progress_callback: callable | None = None,
) -> bool:
    import subprocess
    import cv2

    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        return False

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or frame_width
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or frame_height

    out_w, out_h = (1080, 1920) if actual_h >= 1080 or actual_w >= 1920 else (720, 1280)

    ffmpeg_exe = ffmpeg_bin or "ffmpeg"
    cmd = [
        ffmpeg_exe,
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-s",
        f"{out_w}x{out_h}",
        "-pix_fmt",
        "bgr24",
        "-r",
        f"{fps:.6f}",
        "-i",
        "-",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "18",
        "-c:a",
        "copy",
        "-shortest",
        str(output),
    ]

    proc = None
    writer = None
    try:
        if ffmpeg_exe:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not proc or proc.poll() is not None:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(output), fourcc, fps, (out_w, out_h))
    except Exception:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(output), fourcc, fps, (out_w, out_h))

    frame_idx = 0
    num_frames = len(frames)
    try:
        while True:
            ret, img = cap.read()
            if not ret:
                break

            if frame_idx < num_frames:
                crop = frames[frame_idx].crop_box
            elif num_frames > 0:
                crop = frames[-1].crop_box
            else:
                break

            x1 = int(round(crop.x))
            y1 = int(round(crop.y))
            w = int(round(crop.width))
            h = int(round(crop.height))

            pad_left = max(0, -x1)
            pad_top = max(0, -y1)
            pad_right = max(0, (x1 + w) - actual_w)
            pad_bottom = max(0, (y1 + h) - actual_h)

            if pad_left > 0 or pad_top > 0 or pad_right > 0 or pad_bottom > 0:
                padded_img = cv2.copyMakeBorder(img, pad_top, pad_bottom, pad_left, pad_right, cv2.BORDER_CONSTANT, value=(0, 0, 0))
                src_x = x1 + pad_left
                src_y = y1 + pad_top
                cropped = padded_img[src_y : src_y + h, src_x : src_x + w]
            else:
                cropped = img[y1 : y1 + h, x1 : x1 + w]

            resized = cv2.resize(cropped, (out_w, out_h), interpolation=cv2.INTER_LINEAR)

            if proc and proc.stdin:
                try:
                    proc.stdin.write(resized.tobytes())
                except BrokenPipeError:
                    break
            elif writer:
                writer.write(resized)

            frame_idx += 1
            if progress_callback and (frame_idx % 15 == 0 or frame_idx == num_frames):
                try:
                    progress_callback(frame_idx, max(1, num_frames))
                except Exception:
                    pass
    finally:
        cap.release()
        if proc and proc.stdin:
            try:
                proc.stdin.close()
            except Exception:
                pass
            proc.wait()
        if writer:
            writer.release()

    return output.exists()

