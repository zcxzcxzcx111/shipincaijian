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
    width, height = fit_aspect_size(width, height, frame_width, frame_height, aspect_width, aspect_height)
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

    raw_crops = [
        fit_aspect_around_box(
            frame.subject_box if frame.confidence >= 0.98 else expand_subject_box(frame.subject_box, frame_width, frame_height, margin),
            frame_width,
            frame_height,
            aspect_width,
            aspect_height,
        )
        for frame in track
    ]
    if smooth_radius > 0:
        ws = damping_smooth(median_smooth([box.width for box in raw_crops], smooth_radius))
        hs = damping_smooth(median_smooth([box.height for box in raw_crops], smooth_radius))
        cxs = damping_smooth(median_smooth([frame.subject_box.cx for frame in track], smooth_radius))
        cys = damping_smooth(median_smooth([frame.subject_box.cy for frame in track], smooth_radius))
    else:
        ws = [box.width for box in raw_crops]
        hs = [box.height for box in raw_crops]
        cxs = [frame.subject_box.cx for frame in track]
        cys = [frame.subject_box.cy for frame in track]

    crop_frames: list[CropFrame] = []
    previous: TrackFrame | None = None
    for index, frame in enumerate(track):
        width = max(ws[index], raw_crops[index].width)
        height = max(hs[index], raw_crops[index].height)
        crop_initial = Box(x=cxs[index] - width / 2, y=cys[index] - height / 2, width=width, height=height)
        if frame.confidence >= 0.94:
            w_use = frame.subject_box.width
            h_use = frame.subject_box.height
            crop = center_crop_on_subject(frame.subject_box, w_use, h_use, frame_width, frame_height, allow_outside=False, aspect_width=aspect_width, aspect_height=aspect_height)
        elif frame.confidence >= 0.92:
            crop = center_crop_on_subject(frame.subject_box, width, height, frame_width, frame_height, allow_outside=False, aspect_width=aspect_width, aspect_height=aspect_height)
        else:
            crop = ensure_subject_visible(crop_initial, frame.subject_box, frame_width, frame_height, aspect_width, aspect_height)
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

    # Enforce safety margins around the subject body (head to toe safety check)
    if height < subject.height * 1.12:
        height = subject.height * 1.12
        width = height * target_ratio
    if width < subject.width * 1.12:
        width = subject.width * 1.12
        height = width / target_ratio

    width, height = fit_aspect_size(width, height, frame_width, frame_height, aspect_width, aspect_height)

    # Actively anchor crop center exactly on subject center (`100% 以目标人物中心对齐`)
    desired_cx = subject.cx
    desired_cy = subject.cy

    x = desired_cx - width / 2
    y = desired_cy - height / 2

    # Enforce complete body visibility check
    if x > subject.x - 10:
        x = subject.x - 10
    if x + width < subject.right + 10:
        x = subject.right + 10 - width
    if y > subject.y - 10:
        y = subject.y - 10
    if y + height < subject.bottom + 10:
        y = subject.bottom + 10 - height

    # Strict boundary clamp (`保证不出框`)
    x = clamp(x, 0, max(0, frame_width - width))
    y = clamp(y, 0, max(0, frame_height - height))

    return Box(
        x=x,
        y=y,
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
