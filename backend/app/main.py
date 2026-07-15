from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.app.schemas import AIAnalyzeRequest, AIAnalyzeResponse, AIConfigRequest, CorrectionRequest, JobStatus, TargetRequest
from backend.app.services.ai_client import analyze_frame_with_llm, get_ai_config, update_ai_config
from backend.app.services.pipeline import apply_user_corrections, export_video, run_tracking, select_target
from backend.app.services.storage import create_job_file, job_dir, load_status, save_status


app = FastAPI(title="Single Person Dance Cropper", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/jobs", response_model=JobStatus)
async def create_job(file: UploadFile = File(...)) -> JobStatus:
    return create_job_file(file.filename or "source.mp4", file.file)


@app.post("/api/jobs/{job_id}/target", response_model=JobStatus)
async def target(job_id: str, request: TargetRequest) -> JobStatus:
    try:
        return select_target(job_id, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jobs/{job_id}/track", response_model=JobStatus)
async def track(job_id: str, background_tasks: BackgroundTasks) -> JobStatus:
    try:
        status = load_status(job_id)
        status = save_status(status.model_copy(update={"state": "tracking", "progress": 0.25, "message": "正在跟踪计算中..."}))
        background_tasks.add_task(run_tracking, job_id)
        return status
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或尚未选择目标") from exc


@app.post("/api/jobs/{job_id}/corrections", response_model=JobStatus)
async def corrections(job_id: str, request: CorrectionRequest) -> JobStatus:
    try:
        return apply_user_corrections(job_id, request.corrections)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或尚未完成跟踪") from exc


@app.post("/api/jobs/{job_id}/export", response_model=JobStatus)
async def export(job_id: str, background_tasks: BackgroundTasks) -> JobStatus:
    try:
        status = load_status(job_id)
        status = save_status(status.model_copy(update={"state": "exporting", "progress": 0.85, "message": "正在极速准备视频导出..."}))
        background_tasks.add_task(export_video, job_id)
        return status
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc


@app.get("/api/jobs/{job_id}/status", response_model=JobStatus)
async def status(job_id: str) -> JobStatus:
    try:
        return load_status(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc


@app.get("/api/jobs/{job_id}/download")
async def download(job_id: str) -> FileResponse:
    output = job_dir(job_id) / "output.mp4"
    if not output.exists():
        raise HTTPException(status_code=404, detail="导出文件不存在")
    media_type = "video/mp4" if output.suffix == ".mp4" else "text/plain"
    return FileResponse(Path(output), media_type=media_type, filename=output.name)


@app.get("/api/ai/config")
async def get_ai_config_endpoint() -> dict:
    return get_ai_config()


@app.post("/api/ai/config")
async def update_ai_config_endpoint(request: AIConfigRequest) -> dict:
    return update_ai_config(api_key=request.api_key, base_url=request.base_url, model_name=request.model_name, enabled=request.enabled)


@app.post("/api/jobs/{job_id}/ai-analyze", response_model=AIAnalyzeResponse)
async def ai_analyze_frame(job_id: str, request: AIAnalyzeRequest) -> AIAnalyzeResponse:
    try:
        res = analyze_frame_with_llm(job_id, request.frame_index, request.current_box)
        return AIAnalyzeResponse(**res)
    except Exception as exc:
        return AIAnalyzeResponse(success=False, analysis=f"分析出现异常: {exc}", fallback_reason=str(exc))


