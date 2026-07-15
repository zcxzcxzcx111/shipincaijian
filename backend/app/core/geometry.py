from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class TrackFrame:
    frame_index: int
    subject_box: Box
    confidence: float


@dataclass(frozen=True)
class CropFrame:
    frame_index: int
    subject_box: Box
    crop_box: Box
    confidence: float
    suspicious: bool


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def expand_subject_box(box: Box, frame_width: int, frame_height: int, margin: float = 0.22) -> Box:
    extra_w = box.width * margin
    extra_h = box.height * margin
    x = clamp(box.x - extra_w / 2, 0, frame_width)
    y = clamp(box.y - extra_h / 2, 0, frame_height)
    right = clamp(box.right + extra_w / 2, 0, frame_width)
    bottom = clamp(box.bottom + extra_h / 2, 0, frame_height)
    return Box(x=x, y=y, width=max(1, right - x), height=max(1, bottom - y))


def fit_aspect_around_box(box: Box, frame_width: int, frame_height: int, aspect_width: int = 9, aspect_height: int = 16) -> Box:
    target_ratio = aspect_width / aspect_height
    width = box.width
    height = box.height

    if width / height > target_ratio:
        height = width / target_ratio
    else:
        width = height * target_ratio

    width = min(width, frame_width)
    height = min(height, frame_height)
    if width / height > target_ratio:
        width = height * target_ratio
    else:
        height = width / target_ratio

    x = clamp(box.cx - width / 2, 0, frame_width - width)
    y = clamp(box.cy - height / 2, 0, frame_height - height)

    if x > box.x:
        x = clamp(box.x, 0, frame_width - width)
    if x + width < box.right:
        x = clamp(box.right - width, 0, frame_width - width)
    if y > box.y:
        y = clamp(box.y, 0, frame_height - height)
    if y + height < box.bottom:
        y = clamp(box.bottom - height, 0, frame_height - height)

    return Box(x=x, y=y, width=width, height=height)


def fit_aspect_size(width: float, height: float, frame_width: int, frame_height: int, aspect_width: int = 9, aspect_height: int = 16) -> tuple[float, float]:
    target_ratio = aspect_width / aspect_height
    if width / height > target_ratio:
        height = width / target_ratio
    else:
        width = height * target_ratio

    width = min(width, frame_width)
    height = min(height, frame_height)
    if width / height > target_ratio:
        width = height * target_ratio
    else:
        height = width / target_ratio
    return width, height


def center_crop_on_subject(
    subject: Box,
    width: float,
    height: float,
    frame_width: int,
    frame_height: int,
    allow_outside: bool = False,
    aspect_width: int = 9,
    aspect_height: int = 16,
) -> Box:
    width, height = fit_aspect_size(width, height, 999999, 999999, aspect_width, aspect_height)
    if allow_outside:
        return Box(
            x=subject.cx - width / 2,
            y=subject.cy - height / 2,
            width=width,
            height=height,
        )
    return Box(
        x=clamp(subject.cx - width / 2, 0, max(0, frame_width - width)),
        y=clamp(subject.cy - height / 2, 0, max(0, frame_height - height)),
        width=width,
        height=height,
    )


def median_smooth(values: list[float], radius: int) -> list[float]:
    if radius <= 0 or len(values) < 3:
        return values[:]
    smoothed: list[float] = []
    for index in range(len(values)):
        start = max(0, index - radius)
        end = min(len(values), index + radius + 1)
        smoothed.append(float(median(values[start:end])))
    return smoothed


def damping_smooth(values: list[float], alpha: float = 0.38) -> list[float]:
    if not values or len(values) < 2:
        return values[:]
    forward = [values[0]]
    for val in values[1:]:
        forward.append(forward[-1] * (1.0 - alpha) + val * alpha)
    backward = [forward[-1]]
    for val in reversed(forward[:-1]):
        backward.append(backward[-1] * (1.0 - alpha) + val * alpha)
    backward.reverse()
    return backward


def build_crop_path(
    track: list[TrackFrame],
    frame_width: int,
    frame_height: int,
    margin: float = 0.22,
    confidence_floor: float = 0.55,
    smooth_radius: int = 4,
    aspect_width: int = 9,
    aspect_height: int = 16,
) -> list[CropFrame]:
    if not track:
        return []

    # 1. 计算初始框住时的人物相对画幅比例 (`开始时框住的比例`)
    first_subject = track[0].subject_box
    first_expanded = expand_subject_box(first_subject, frame_width, frame_height, margin)
    init_w, init_h = fit_aspect_size(first_expanded.width, first_expanded.height, 999999, 999999, aspect_width, aspect_height)
    
    scale_ratio_h = init_h / max(1.0, first_subject.height)
    target_ratio = aspect_width / aspect_height

    # 2. 逐帧生成保持初版比例且完全以人物为中心的目标框
    raw_ws: list[float] = []
    raw_hs: list[float] = []
    for frame in track:
        # 严格按开始时的人物高宽比例计算当前帧目标框大小
        target_h = max(32.0, frame.subject_box.height * scale_ratio_h)
        target_w = target_h * target_ratio
        # 保障包覆全身及边界安全边距
        if target_w < frame.subject_box.width * 1.15:
            target_w = frame.subject_box.width * 1.15
            target_h = target_w / target_ratio
        if target_h < frame.subject_box.height * 1.15:
            target_h = frame.subject_box.height * 1.15
            target_w = target_h * target_ratio
        raw_ws.append(target_w)
        raw_hs.append(target_h)

    if smooth_radius > 0:
        ws = damping_smooth(median_smooth(raw_ws, smooth_radius))
        hs = damping_smooth(median_smooth(raw_hs, smooth_radius))
        cxs = damping_smooth(median_smooth([frame.subject_box.cx for frame in track], smooth_radius))
        cys = damping_smooth(median_smooth([frame.subject_box.cy for frame in track], smooth_radius))
    else:
        ws = raw_ws
        hs = raw_hs
        cxs = [frame.subject_box.cx for frame in track]
        cys = [frame.subject_box.cy for frame in track]

    crop_frames: list[CropFrame] = []
    previous: TrackFrame | None = None
    for index, frame in enumerate(track):
        width = ws[index]
        height = hs[index]
        # 严格居中：画幅的正中央就是目标人物的中心 (`始终保持这个中心在画幅的正中央`)
        crop = Box(
            x=cxs[index] - width / 2,
            y=cys[index] - height / 2,
            width=width,
            height=height,
        )
        jump = 0.0 if previous is None else abs(frame.subject_box.cx - previous.subject_box.cx) + abs(frame.subject_box.cy - previous.subject_box.cy)
        suspicious = frame.confidence < confidence_floor or jump > max(frame_width, frame_height) * 0.18
        crop_frames.append(
            CropFrame(
                frame_index=frame.frame_index,
                subject_box=frame.subject_box,
                crop_box=crop,
                confidence=frame.confidence,
                suspicious=suspicious,
            )
        )
        previous = frame
    return crop_frames


def ensure_subject_visible(
    crop: Box,
    subject: Box,
    frame_width: int,
    frame_height: int,
    aspect_width: int = 9,
    aspect_height: int = 16,
) -> Box:
    width = crop.width
    height = crop.height
    target_ratio = aspect_width / aspect_height

    if height < subject.height * 1.15:
        height = subject.height * 1.15
        width = height * target_ratio
    if width < subject.width * 1.15:
        width = subject.width * 1.15
        height = width / target_ratio

    width, height = fit_aspect_size(width, height, 999999, 999999, aspect_width, aspect_height)

    # Actively anchor crop center exactly on subject center (`100% 以目标人物中心对齐`)
    return Box(
        x=subject.cx - width / 2,
        y=subject.cy - height / 2,
        width=width,
        height=height,
    )


def apply_corrections(track: list[TrackFrame], corrections: dict[int, Box]) -> list[TrackFrame]:
    if not corrections:
        return track[:]
    
    # First apply exact manual corrections
    corrected: list[TrackFrame] = []
    for frame in track:
        replacement = corrections.get(frame.frame_index)
        corrected.append(
            TrackFrame(
                frame_index=frame.frame_index,
                subject_box=replacement or frame.subject_box,
                confidence=0.98 if replacement else frame.confidence,
            )
        )

    # Keyframe interpolation across gaps between anchor frames
    # Anchor frames: any frame that was corrected OR has very high detection confidence
    anchor_indices = [
        idx for idx, f in enumerate(corrected)
        if f.frame_index in corrections or f.confidence >= 0.94
    ]
    if len(anchor_indices) >= 2:
        for i in range(len(anchor_indices) - 1):
            start_idx = anchor_indices[i]
            end_idx = anchor_indices[i + 1]
            if end_idx - start_idx > 1:
                # Check if gap needs interpolation (e.g., contains medium/low confidence frames or connects to a user correction)
                has_suspicious = any(f.confidence < 0.88 for f in corrected[start_idx + 1:end_idx])
                start_corrected = corrected[start_idx].frame_index in corrections
                end_corrected = corrected[end_idx].frame_index in corrections
                if has_suspicious or start_corrected or end_corrected:
                    box_s = corrected[start_idx].subject_box
                    box_e = corrected[end_idx].subject_box
                    steps = end_idx - start_idx
                    for step in range(1, steps):
                        t = step / steps
                        interp_box = Box(
                            x=box_s.x + (box_e.x - box_s.x) * t,
                            y=box_s.y + (box_e.y - box_s.y) * t,
                            width=box_s.width + (box_e.width - box_s.width) * t,
                            height=box_s.height + (box_e.height - box_s.height) * t,
                        )
                        curr_frame = corrected[start_idx + step]
                        corrected[start_idx + step] = TrackFrame(
                            frame_index=curr_frame.frame_index,
                            subject_box=interp_box,
                            confidence=max(0.95 if (start_corrected or end_corrected) else 0.92, curr_frame.confidence),
                        )
    return corrected
