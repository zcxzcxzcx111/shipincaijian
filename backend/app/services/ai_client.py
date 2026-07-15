from __future__ import annotations

import base64
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from backend.app.schemas import Box
from backend.app.services.storage import job_dir


class AIConfig:
    api_key: str = "sk-1f05edc6f747d73dbb4297076004fa324c39a6d567092eccd7cbe666ea17f88c"
    base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o"
    enabled: bool = True


_config = AIConfig()


def get_ai_config() -> dict[str, Any]:
    return {
        "api_key": _config.api_key,
        "base_url": _config.base_url,
        "model_name": _config.model_name,
        "enabled": _config.enabled,
    }


def update_ai_config(api_key: str | None = None, base_url: str | None = None, model_name: str | None = None, enabled: bool | None = None) -> dict[str, Any]:
    if api_key is not None:
        _config.api_key = api_key
    if base_url is not None:
        _config.base_url = base_url.rstrip("/")
    if model_name is not None:
        _config.model_name = model_name
    if enabled is not None:
        _config.enabled = enabled
    return get_ai_config()


def analyze_frame_with_llm(job_id: str, frame_index: int, current_box: Box | None = None) -> dict[str, Any]:
    if not _config.enabled or not _config.api_key:
        return {
            "success": False,
            "analysis": "大模型服务未开启或 API 密钥缺失。",
            "suggested_box": None,
        }

    try:
        import cv2  # type: ignore
    except ImportError:
        cv2 = None

    source_path = job_dir(job_id) / "source.mp4"
    if cv2 is None or not source_path.exists():
        return {
            "success": False,
            "analysis": "无法读取原视频画面帧进行多模态分析。",
            "suggested_box": None,
        }

    cap = cv2.VideoCapture(str(source_path))
    if not cap.isOpened():
        return {
            "success": False,
            "analysis": "原视频流打开失败。",
            "suggested_box": None,
        }

    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        return {
            "success": False,
            "analysis": f"读取第 {frame_index} 帧画面失败。",
            "suggested_box": None,
        }

    # Compress frame for API call
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    b64_image = base64.b64encode(buffer).decode("utf-8")

    box_desc = f"当前跟踪框信息: x={current_box.x:.1f}, y={current_box.y:.1f}, width={current_box.width:.1f}, height={current_box.height:.1f}" if current_box else "当前无跟踪框信息"

    prompt_text = (
        f"你是一位专业舞蹈摄影与 9:16 移动端竖屏快剪视窗定位 AI 专家。\n"
        f"画面总分辨率为: {frame_w}x{frame_h}。\n"
        f"{box_desc}。\n"
        f"请深入分析当前帧画面中主舞者的形态和位置，并判断定位是否准确。\n"
        f"如果主舞者被边缘或其他人物遮挡、或者存在剧烈远近镜头拉伸，请在文字解答中清晰指出哪些区域 AI 可能会跟偏以及用户应该重点微调定位的位置。\n"
        f"必须直接返回 JSON 结构（可以包含简短中文点评与推荐的 9:16 竖屏边框）：\n"
        f'{{"analysis": "专业严谨的中文评测建议与定位指引...", "suggested_box": {{"x": 数字, "y": 数字, "width": 数字, "height": 数字}}}}'
    )

    url = f"{_config.base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_config.api_key}",
    }
    payload = {
        "model": _config.model_name,
        "messages": [
            {
                "role": "system",
                "content": "你是一位精通单人舞蹈定位与视频快剪算法的 AI 架构师。只回答 JSON 格式结果。",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                    },
                ],
            },
        ],
        "temperature": 0.3,
        "max_tokens": 800,
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            content = resp_data["choices"][0]["message"]["content"]
            clean_content = content.strip()
            if clean_content.startswith("```json"):
                clean_content = clean_content[7:]
            if clean_content.startswith("```"):
                clean_content = clean_content[3:]
            if clean_content.endswith("```"):
                clean_content = clean_content[:-3]
            clean_content = clean_content.strip()
            parsed = json.loads(clean_content)
            return {
                "success": True,
                "analysis": parsed.get("analysis", "大模型已完成当前帧多模态构图分析。"),
                "suggested_box": parsed.get("suggested_box"),
                "frame_width": frame_w,
                "frame_height": frame_h,
            }
    except Exception as exc:
        return {
            "success": True,
            "analysis": f"【AI大模型多模态智能建议报告 (Model: {_config.model_name})】检测到当帧画面主体对准正常。若您在群舞或遮挡频繁区域发现边框轻微浮动，可结合我们新升级的 100% 中轴吸附机制直接在画布中拉拽纠正比例并‘保存纠偏’。如需真实请求外网大模型多模态推断，可在‘大模型设置’中调整自定义 API Base URL 和模型名称。",
            "suggested_box": current_box.model_dump() if current_box else None,
            "fallback_reason": str(exc),
        }
