# 单人锁定裁剪工具

本项目是一个本地 Web 工具的第一版实现，用于在群众跳舞视频中点选并锁定一个人，生成稳定的 9:16 全身优先裁剪轨迹，并导出成片。

当前实现包含：

- React/Vite 前端源码：上传、点选目标、低置信度片段、关键帧纠偏、导出状态。
- FastAPI 后端源码：任务 API、目标选择、跟踪、纠偏、导出接口。
- 纯 Python 核心算法：人物框扩展、9:16 裁剪约束、轨迹平滑、低置信度标记、纠偏合并。
- 模型适配层：第一版提供确定性 MVP 跟踪器；SAM2、YOLO/ReID、FFmpeg 作为可插拔生产依赖接入。

## 安装

Windows 一键启动：

```powershell
.\start-dev.cmd
```

脚本会打开两个服务窗口，并自动打开 `http://127.0.0.1:5173`。

前端：

```powershell
pnpm install
pnpm run dev
```

后端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

只启动 API 可先安装 `requirements-core.txt`。生产级视频处理还需要安装 FFmpeg，并按需安装 `requirements-models.txt`、SAM2、PyTorch GPU 版本。

## API

- `POST /api/jobs` 上传视频并创建任务。
- `POST /api/jobs/{id}/target` 提交目标帧和正/负点击点或框选区域。
- `POST /api/jobs/{id}/track` 启动或重跑跟踪。
- `POST /api/jobs/{id}/corrections` 保存关键帧纠偏。
- `POST /api/jobs/{id}/export` 导出 9:16 视频。
- `GET /api/jobs/{id}/status` 查询进度、置信度和下载地址。

## 测试

核心算法测试不依赖 FastAPI、OpenCV 或 FFmpeg：

```powershell
python -m unittest discover -s backend/tests
```
