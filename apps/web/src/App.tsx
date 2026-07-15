import { BoxSelect, Check, Crosshair, Download, Film, MousePointer2, Play, RefreshCw, Settings, Sparkles, Trash2, Undo2, Upload, X } from "lucide-react";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { analyzeFrameWithAI, createJob, exportJob, getAIConfig, getStatus, startTracking, submitCorrection, submitTarget, updateAIConfig } from "./api";
import type { AIAnalyzeResponse, AIConfig, Box, JobStatus, Point } from "./types";

const fallbackFrameWidth = 1280;
const fallbackFrameHeight = 720;
const fallbackFps = 30;

type PointMode = "box" | "positive" | "negative";
type FramePoint = Point & { frameIndex: number };
type FrameBox = Box & { frameIndex: number };

const text = {
  appTitle: "\u5355\u4eba\u9501\u5b9a\u88c1\u526a",
  upload: "\u4e0a\u4f20\u89c6\u9891",
  task: "\u4efb\u52a1",
  waitingUpload: "\u7b49\u5f85\u4e0a\u4f20",
  framePoints: "\u76ee\u6807\u6807\u8bb0\u70b9",
  tracking: "\u8ddf\u8e2a",
  notStarted: "\u672a\u5f00\u59cb",
  export: "\u5bfc\u51fa",
  downloadable: "\u53ef\u4e0b\u8f7d",
  notExported: "\u672a\u5bfc\u51fa",
  positivePoint: "\u76ee\u6807\u70b9",
  negativePoint: "\u6392\u9664\u70b9",
  boxPerson: "\u6846\u9009\u4eba\u7269",
  confirmBox: "\u786e\u5b9a\u6846\u9009",
  cancelBox: "\u53d6\u6d88\u6846\u9009",
  undo: "\u64a4\u9500\u4e0a\u4e00\u4e2a",
  clearCurrent: "\u6e05\u7a7a\u672c\u5e27",
  lockTarget: "\u9501\u5b9a\u76ee\u6807",
  startTracking: "\u5f00\u59cb\u8ddf\u8e2a",
  saveCorrection: "\u4fdd\u5b58\u7ea0\u504f",
  export916: "\u5bfc\u51fa 9:16",
  waitingVideo: "\u7b49\u5f85\u89c6\u9891",
  currentFrame: "\u5f53\u524d\u5e27",
  redSegments: "\u7ea2\u8272\u7247\u6bb5\u9700\u8981\u68c0\u67e5",
};

export function App() {
  const [job, setJob] = useState<JobStatus | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [points, setPoints] = useState<FramePoint[]>([]);
  const [boxes, setBoxes] = useState<FrameBox[]>([]);
  const [draftBox, setDraftBox] = useState<Box | null>(null);
  const [standardBoxSize, setStandardBoxSize] = useState<{ width: number; height: number } | null>(null);
  const [pointMode, setPointMode] = useState<PointMode>("box");
  const [selectedFrame, setSelectedFrame] = useState(0);
  const [videoMeta, setVideoMeta] = useState<{ width: number; height: number } | null>(null);
  const [message, setMessage] = useState("\u4e0a\u4f20\u89c6\u9891\u540e\uff0c\u5728\u753b\u9762\u4e2d\u70b9\u9009\u8981\u9501\u5b9a\u7684\u4eba\u3002");
  const [busy, setBusy] = useState(false);
  const [aiModalOpen, setAiModalOpen] = useState(false);
  const [aiConfigOpen, setAiConfigOpen] = useState(false);
  const [aiConfig, setAiConfig] = useState<AIConfig | null>(null);
  const [aiAnalysis, setAiAnalysis] = useState<AIAnalyzeResponse | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const videoLayerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const dragStartRef = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    getAIConfig().then(setAiConfig).catch(() => {});
  }, []);

  useEffect(() => {
    if (!job || (job.state !== "tracking" && job.state !== "exporting")) return;
    setBusy(true);
    const timer = setInterval(async () => {
      try {
        const latest = await getStatus(job.id);
        setJob(latest);
        if (latest.message) {
          setMessage(latest.message);
        }
        if (latest.state !== "tracking" && latest.state !== "exporting") {
          setBusy(false);
        }
      } catch {
        // ignore polling errors
      }
    }, 350);
    return () => clearInterval(timer);
  }, [job?.id, job?.state]);

  const suspiciousSet = useMemo(() => new Set(job?.suspicious_frames ?? []), [job]);
  const currentPoints = points.filter((point) => point.frameIndex === selectedFrame);
  const currentBox = boxes.find((box) => box.frameIndex === selectedFrame);
  const currentTrack = job?.tracking_frames?.find((frame) => frame.frame_index === selectedFrame);
  const currentPositiveCount = currentPoints.filter((point) => point.label === "positive").length;
  const currentNegativeCount = currentPoints.filter((point) => point.label === "negative").length;
  const totalPositiveCount = points.filter((point) => point.label === "positive").length;
  const totalNegativeCount = points.filter((point) => point.label === "negative").length;
  const totalBoxCount = boxes.length;
  const frameWidth = job?.width ?? videoMeta?.width ?? fallbackFrameWidth;
  const frameHeight = job?.height ?? videoMeta?.height ?? fallbackFrameHeight;

  async function run<T>(label: string, action: () => Promise<T>, after?: (result: T) => void) {
    setBusy(true);
    setMessage(label);
    try {
      const result = await action();
      after?.(result);
      if (result && typeof result === "object" && "state" in result) {
        const state = (result as { state: string }).state;
        if (state === "tracking" || state === "exporting") {
          return;
        }
      }
      setMessage("\u5b8c\u6210");
      setBusy(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "\u64cd\u4f5c\u5931\u8d25");
      setBusy(false);
    }
  }

  function selectFrame(frame: number) {
    if (videoRef.current && !videoRef.current.paused) {
      videoRef.current.pause();
    }
    setSelectedFrame(frame);
    if (videoRef.current) {
      const nextTime = frame / fallbackFps;
      if (Number.isFinite(videoRef.current.duration)) {
        videoRef.current.currentTime = Math.min(nextTime, videoRef.current.duration);
      }
    }
  }

  function onVideoTimeUpdate() {
    if (!videoRef.current) return;
    if (!videoRef.current.paused) {
      setSelectedFrame(Math.round(videoRef.current.currentTime * fallbackFps));
    }
  }

  function getStagePoint(event: React.MouseEvent<HTMLDivElement>): { x: number; y: number } | null {
    if (!videoLayerRef.current) return null;
    const rect = videoLayerRef.current.getBoundingClientRect();
    const relativeX = (event.clientX - rect.left) / rect.width;
    const relativeY = (event.clientY - rect.top) / rect.height;
    if (relativeX < 0 || relativeX > 1 || relativeY < 0 || relativeY > 1) {
      return null;
    }
    const x = Math.round(relativeX * frameWidth);
    const y = Math.round(relativeY * frameHeight);
    return {
      x: Math.max(0, Math.min(frameWidth, x)),
      y: Math.max(0, Math.min(frameHeight, y)),
    };
  }

  function boxFromPoints(start: { x: number; y: number }, end: { x: number; y: number }): Box {
    const rawW = Math.abs(end.x - start.x);
    const rawH = Math.abs(end.y - start.y);
    if (standardBoxSize && rawW < 12 && rawH < 12) {
      return boxAroundCenter(end, standardBoxSize.width, standardBoxSize.height);
    }
    const height = Math.max(20, Math.max(rawH, rawW * (16 / 9)));
    const width = height * (9 / 16);
    const cx = (start.x + end.x) / 2;
    const cy = (start.y + end.y) / 2;
    return clampBoxToFrame({
      x: cx - width / 2,
      y: cy - height / 2,
      width,
      height,
    });
  }

  function boxAroundCenter(center: { x: number; y: number }, width: number, height: number): Box {
    const h = Math.max(20, height);
    const w = h * (9 / 16);
    return clampBoxToFrame({
      x: center.x - w / 2,
      y: center.y - h / 2,
      width: w,
      height: h,
    });
  }

  function applyStandardSize(box: Box): Box {
    if (!standardBoxSize) return clampBoxToFrame(box);
    return boxAroundCenter(
      {
        x: box.x + box.width / 2,
        y: box.y + box.height / 2,
      },
      standardBoxSize.width,
      standardBoxSize.height,
    );
  }

  function clampBoxToFrame(box: Box): Box {
    const width = Math.max(1, Math.min(box.width, frameWidth));
    const height = Math.max(1, Math.min(box.height, frameHeight));
    return {
      x: Math.max(0, Math.min(frameWidth - width, box.x)),
      y: Math.max(0, Math.min(frameHeight - height, box.y)),
      width,
      height,
    };
  }

  function defaultBoxFromPoint(point: Point): Box {
    const height = Math.min(640, Math.max(180, frameHeight * 0.55));
    const width = height * (9 / 16);
    return clampBoxToFrame({
      x: point.x - width / 2,
      y: point.y - height / 2,
      width,
      height,
    });
  }

  function onPreviewMouseDown(event: React.MouseEvent<HTMLDivElement>) {
    if (videoRef.current && !videoRef.current.paused) {
      videoRef.current.pause();
    }
    if (pointMode !== "box") return;
    const point = getStagePoint(event);
    if (!point) return;
    dragStartRef.current = point;
    setDraftBox({ x: point.x, y: point.y, width: 1, height: 1 });
    event.preventDefault();
  }

  function onPreviewMouseMove(event: React.MouseEvent<HTMLDivElement>) {
    if (pointMode !== "box" || !dragStartRef.current) return;
    const point = getStagePoint(event);
    if (!point) return;
    setDraftBox(boxFromPoints(dragStartRef.current, point));
  }

  function onPreviewMouseUp(event: React.MouseEvent<HTMLDivElement>) {
    if (pointMode !== "box" || !dragStartRef.current) return;
    const point = getStagePoint(event);
    const start = dragStartRef.current;
    dragStartRef.current = null;
    if (!point) return;
    const box = boxFromPoints(start, point);
    if (box.width < 20 || box.height < 20) {
      setDraftBox(null);
      setMessage("\u6846\u592a\u5c0f\u4e86\uff0c\u8bf7\u62d6\u51fa\u4e00\u4e2a\u80fd\u5305\u4f4f\u4eba\u7269\u5168\u8eab\u7684\u6846\u3002");
      return;
    }
    setDraftBox(box);
    setMessage(`\u5df2\u5728\u7b2c ${selectedFrame} \u5e27\u753b\u51fa 9:16 \u5f85\u786e\u8ba4\u6846 (${Math.round(box.width)}x${Math.round(box.height)})\uff0c\u53ef\u81ea\u7531\u7f29\u653e\u8c03\u8282\u5927\u5c0f\uff0c\u70b9\u51fb\u201c\u786e\u5b9a\u6846\u9009\u201d\u540e\u751f\u6548\u3002`);
  }

  function confirmDraftBox() {
    if (videoRef.current && !videoRef.current.paused) {
      videoRef.current.pause();
    }
    if (!draftBox) {
      setMessage("\u5148\u62d6\u62fd\u6846\u9009\u4eba\u7269\uff0c\u518d\u786e\u5b9a\u6846\u9009\u3002");
      return;
    }
    const box = clampBoxToFrame(draftBox);
    const frameBox = { ...box, frameIndex: selectedFrame };
    const centerPoint: FramePoint = {
      x: Math.round(box.x + box.width / 2),
      y: Math.round(box.y + box.height / 2),
      label: "positive",
      frameIndex: selectedFrame,
    };
    setBoxes((current) => [...current.filter((item) => item.frameIndex !== selectedFrame), frameBox]);
    setPoints((current) => [
      ...current.filter((item) => !(item.frameIndex === selectedFrame && item.label === "positive")),
      centerPoint,
    ]);
    setStandardBoxSize({ width: box.width, height: box.height });
    setDraftBox(null);
    setMessage(`\u5df2\u786e\u8ba4\u7b2c ${selectedFrame} \u5e27\u7684 9:16 \u4eba\u7269\u6846 (${Math.round(box.width)}x${Math.round(box.height)})\u3002`);
  }

  function cancelDraftBox() {
    setDraftBox(null);
    dragStartRef.current = null;
    setMessage("\u5df2\u53d6\u6d88\u5f85\u786e\u8ba4\u6846\u3002");
  }

  function onPreviewClick(event: React.MouseEvent<HTMLDivElement>) {
    if (videoRef.current && !videoRef.current.paused) {
      videoRef.current.pause();
    }
    if (pointMode === "box") return;
    const point = getStagePoint(event);
    if (!point) return;
    const { x, y } = point;
    const label = event.altKey ? "negative" : pointMode;
    setPoints((current) => [...current, { x, y, label, frameIndex: selectedFrame }]);
    setMessage(
      label === "positive"
        ? `\u5df2\u5728\u7b2c ${selectedFrame} \u5e27\u6dfb\u52a0\u76ee\u6807\u70b9\u3002`
        : `\u5df2\u5728\u7b2c ${selectedFrame} \u5e27\u6dfb\u52a0\u6392\u9664\u70b9\u3002`,
    );
  }

  async function onFileSelected(file?: File) {
    if (!file) return;
    setSelectedFile(file);
    setVideoUrl(URL.createObjectURL(file));
    setVideoMeta(null);
    setJob(null);
    setPoints([]);
    setBoxes([]);
    setDraftBox(null);
    setStandardBoxSize(null);
    setSelectedFrame(0);
    await run("\u521b\u5efa\u4efb\u52a1\u4e2d...", () => createJob(file), setJob);
  }

  function undoPoint() {
    if (currentBox) {
      setBoxes((current) => {
        const next = current.filter((box) => box.frameIndex !== selectedFrame);
        if (next.length === 0) setStandardBoxSize(null);
        return next;
      });
      setPoints((current) => current.filter((point) => !(point.frameIndex === selectedFrame && point.label === "positive")));
      setMessage(`\u5df2\u64a4\u9500\u7b2c ${selectedFrame} \u5e27\u7684\u4eba\u7269\u6807\u51c6\u6846\u3002`);
      return;
    }
    const lastCurrentIndex = points.map((point, index) => ({ point, index })).reverse().find((item) => item.point.frameIndex === selectedFrame)?.index;
    if (lastCurrentIndex === undefined) {
      setMessage("\u5f53\u524d\u5e27\u6ca1\u6709\u53ef\u64a4\u9500\u7684\u70b9\u3002");
      return;
    }
    setPoints((current) => current.filter((_, index) => index !== lastCurrentIndex));
    setMessage(`\u5df2\u64a4\u9500\u7b2c ${selectedFrame} \u5e27\u7684\u4e0a\u4e00\u4e2a\u70b9\u3002`);
  }

  function clearCurrentFramePoints() {
    setPoints((current) => current.filter((point) => point.frameIndex !== selectedFrame));
    setBoxes((current) => {
      const next = current.filter((box) => box.frameIndex !== selectedFrame);
      if (next.length === 0) setStandardBoxSize(null);
      return next;
    });
    setDraftBox(null);
    setMessage(`\u5df2\u6e05\u7a7a\u7b2c ${selectedFrame} \u5e27\u7684\u6807\u8bb0\u70b9\u548c\u4eba\u7269\u6846\u3002`);
  }

  function handleLockTarget() {
    if (videoRef.current && !videoRef.current.paused) {
      videoRef.current.pause();
    }
    if (!job && !selectedFile) {
      setMessage("\u8bf7\u5148\u4e0a\u4f20\u89c6\u9891\u3002");
      return;
    }
    if (draftBox && !currentBox) {
      setMessage("\u5f53\u524d\u5e27\u6709\u5f85\u786e\u8ba4\u6846\uff0c\u5148\u70b9\u51fb\u201c\u786e\u5b9a\u6846\u9009\u201d\u518d\u9501\u5b9a\u76ee\u6807\u3002");
      return;
    }
    if (currentPositiveCount === 0 && !currentBox) {
      setMessage("\u5148\u5728\u5f53\u524d\u5e27\u6846\u9009\u4eba\u7269\uff0c\u6216\u6dfb\u52a0\u76ee\u6807\u70b9\uff0c\u518d\u9501\u5b9a\u76ee\u6807\u3002");
      return;
    }
    const requestPoints: Point[] = currentPoints.map(({ frameIndex: _frameIndex, ...point }) => point);
    run(
      "\u63d0\u4ea4\u76ee\u6807\u4e2d...",
      async () => {
        const activeJob = job ?? (await createJob(selectedFile!));
        return submitTarget(activeJob.id, selectedFrame, requestPoints, targetBox);
      },
      setJob,
    );
  }

  function handleStartTracking() {
    if (!job && !selectedFile) {
      setMessage("\u8bf7\u5148\u4e0a\u4f20\u89c6\u9891\u3002");
      return;
    }
    if (draftBox && !currentBox) {
      setMessage("\u5f53\u524d\u5e27\u6709\u5f85\u786e\u8ba4\u6846\uff0c\u5148\u70b9\u51fb\u201c\u786e\u5b9a\u6846\u9009\u201d\u518d\u5f00\u59cb\u8ddf\u8e2a\u3002");
      return;
    }
    if (!job || job.state === "created") {
      const frameWithTarget = boxes[0]?.frameIndex ?? points.find((point) => point.label === "positive")?.frameIndex;
      if (frameWithTarget === undefined) {
        setMessage("\u5148\u5728\u4efb\u610f\u4e00\u5e27\u6846\u9009\u4eba\u7269\uff0c\u6216\u6dfb\u52a0\u76ee\u6807\u70b9\uff0c\u518d\u5f00\u59cb\u8ddf\u8e2a\u3002");
        return;
      }
      const framePoints = pointsForFrame(frameWithTarget);
      const frameBox = targetBoxForFrame(frameWithTarget);
      run(
        `\u6b63\u5728\u4f7f\u7528\u7b2c ${frameWithTarget} \u5e27\u7684\u4eba\u7269\u6807\u51c6\u6846\u9501\u5b9a\u5e76\u5f00\u59cb\u8ddf\u8e2a...`,
        async () => {
          const activeJob = job ?? (await createJob(selectedFile!));
          await submitTarget(activeJob.id, frameWithTarget, framePoints, frameBox);
          return startTracking(activeJob.id);
        },
        setJob,
      );
      return;
    }
    run("\u8ddf\u8e2a\u8ba1\u7b97\u4e2d...", () => startTracking(job.id), setJob);
  }

  function handleSaveCorrection() {
    if (videoRef.current && !videoRef.current.paused) {
      videoRef.current.pause();
    }
    if (!job) {
      setMessage("\u8bf7\u5148\u4e0a\u4f20\u89c6\u9891\u3002");
      return;
    }
    if (draftBox && !currentBox) {
      setMessage("\u5f53\u524d\u5e27\u6709\u5f85\u786e\u8ba4\u6846\uff0c\u5148\u70b9\u51fb\u201c\u786e\u5b9a\u6846\u9009\u201d\u518d\u4fdd\u5b58\u7ea0\u504f\u3002");
      return;
    }
    if (!targetBox) {
      setMessage("\u5148\u5728\u5f53\u524d\u5e27\u6dfb\u52a0\u76ee\u6807\u70b9\uff0c\u624d\u80fd\u4fdd\u5b58\u8fd9\u4e00\u5e27\u7684\u7ea0\u504f\u3002");
      return;
    }
    run("\u4fdd\u5b58\u7ea0\u504f\u4e2d...", () => submitCorrection(job.id, selectedFrame, targetBox), setJob);
  }

  function handleExport() {
    if (!job) {
      setMessage("\u8bf7\u5148\u4e0a\u4f20\u89c6\u9891\u5e76\u5b8c\u6210\u8ddf\u8e2a\u3002");
      return;
    }
    if (job.state !== "tracked" && job.state !== "exported") {
      setMessage("\u5148\u5b8c\u6210\u76ee\u6807\u9501\u5b9a\u548c\u8ddf\u8e2a\uff0c\u518d\u5bfc\u51fa\u89c6\u9891\u3002");
      return;
    }
    run("\u5bfc\u51fa\u4e2d...", () => exportJob(job.id), setJob);
  }

  async function handleAIAnalyze() {
    if (!job) {
      setMessage("请先上传视频，才能让大模型评估画面结构。");
      return;
    }
    setBusy(true);
    setMessage(`多模态大模型 (${aiConfig?.model_name ?? "gpt-4o"}) 正在评估第 ${selectedFrame} 帧构图...`);
    setAiModalOpen(true);
    try {
      const result = await analyzeFrameWithAI(job.id, selectedFrame, targetBox);
      setAiAnalysis(result);
      setMessage("大模型多模态评估完成。");
    } catch (error) {
      setAiAnalysis({
        success: false,
        analysis: `大模型连接失败: ${error instanceof Error ? error.message : "未知网络或代理设置错误"}`,
      });
      setMessage("大模型请求异常。");
    } finally {
      setBusy(false);
    }
  }

  function applyAIBox(box: Box) {
    const clamped = clampBoxToFrame(box);
    if (!clamped) return;
    const next = boxes.filter((item) => item.frameIndex !== selectedFrame);
    next.push({ ...clamped, frameIndex: selectedFrame });
    setBoxes(next);
    setStandardBoxSize({ width: clamped.width, height: clamped.height });
    setAiModalOpen(false);
    setMessage(`已应用 AI 推荐的 ${Math.round(clamped.width)}x${Math.round(clamped.height)} 选框到第 ${selectedFrame} 帧。`);
  }

  const primaryPoint = currentPoints.find((point) => point.label === "positive");
  const targetBox: Box | undefined = currentBox ? clampBoxToFrame(currentBox) : primaryPoint ? defaultBoxFromPoint(primaryPoint) : undefined;

  function pointsForFrame(frameIndex: number): Point[] {
    return points.filter((point) => point.frameIndex === frameIndex).map(({ frameIndex: _frameIndex, ...point }) => point);
  }

  function targetBoxForFrame(frameIndex: number): Box | undefined {
    const box = boxes.find((item) => item.frameIndex === frameIndex);
    if (box) {
      const { frameIndex: _frameIndex, ...target } = box;
      return clampBoxToFrame(target);
    }
    const point = points.find((item) => item.frameIndex === frameIndex && item.label === "positive");
    if (!point) return undefined;
    return defaultBoxFromPoint(point);
  }

  return (
    <main className="app-shell">
      <aside className="side-panel">
        <div>
          <p className="eyebrow">Dance Focus Cropper</p>
          <h1>{text.appTitle}</h1>
        </div>

        <label className="upload-control">
          <Upload size={18} />
          <span>{text.upload}</span>
          <input type="file" accept="video/*" onChange={(event) => onFileSelected(event.target.files?.[0])} />
        </label>

        <div className="step-list">
          <Step active={!!job} title={text.task} value={job?.id ?? text.waitingUpload} />
          <Step
            active={currentPoints.length > 0 || !!draftBox}
            title={text.framePoints}
            value={`\u672c\u5e27\u6846 ${currentBox ? 1 : 0} \u00b7 \u5f85\u786e\u8ba4 ${draftBox ? 1 : 0} \u00b7 \u5168\u90e8\u6846 ${totalBoxCount}`}
          />
          <Step active={job?.state === "tracked" || job?.state === "exported"} title={text.tracking} value={job?.state ?? text.notStarted} />
          <Step active={job?.state === "exported"} title={text.export} value={job?.download_url ? text.downloadable : text.notExported} />
        </div>

        <section className="point-editor" aria-label={text.framePoints}>
          <div>
            <h2>{text.framePoints}</h2>
            <p>
              {"\u5148\u7528\u201c\u6846\u9009\u4eba\u7269\u201d\u628a\u4eba\u7269\u5168\u8eab\u6846\u597d\uff0c\u8fd9\u4e2a\u6846\u4f1a\u6210\u4e3a\u540e\u7eed\u8ddf\u8e2a\u7684\u6807\u51c6\u5927\u5c0f\u548c\u4e2d\u5fc3\u57fa\u51c6\u3002"}
            </p>
          </div>
          <div className="mode-toggle" role="group" aria-label={text.framePoints}>
            <button className={pointMode === "box" ? "selected" : ""} onClick={() => setPointMode("box")}>
              <BoxSelect size={16} /> {text.boxPerson}
            </button>
            <button className={pointMode === "positive" ? "selected" : ""} onClick={() => setPointMode("positive")}>
              <MousePointer2 size={16} /> {text.positivePoint}
            </button>
          </div>
          <div className="mode-toggle" role="group" aria-label={text.framePoints}>
            <button className={pointMode === "negative" ? "selected" : ""} onClick={() => setPointMode("negative")}>
              <MousePointer2 size={16} /> {text.negativePoint}
            </button>
          </div>
          <div className="point-actions">
            <button disabled={!draftBox} onClick={confirmDraftBox}>
              <Check size={16} /> {text.confirmBox}
            </button>
            <button disabled={!draftBox} onClick={cancelDraftBox}>
              <X size={16} /> {text.cancelBox}
            </button>
            <button disabled={currentPoints.length === 0} onClick={undoPoint}>
              <Undo2 size={16} /> {text.undo}
            </button>
            <button disabled={currentPoints.length === 0} onClick={clearCurrentFramePoints}>
              <Trash2 size={16} /> {text.clearCurrent}
            </button>
          </div>
          <p className="point-help">
            {`\u5f53\u524d\u5e27\uff1a${selectedFrame}\u3002\u62d6\u51fa\u6846\u540e\u9700\u8981\u70b9\u51fb\u201c\u786e\u5b9a\u6846\u9009\u201d\uff1b${standardBoxSize ? `\u6807\u51c6\u5c3a\u5bf8\uff1a${Math.round(standardBoxSize.width)}x${Math.round(standardBoxSize.height)}\uff0c\u540e\u7eed\u6846\u9009\u53ea\u6539\u4e2d\u5fc3\u3002` : "\u7b2c\u4e00\u6b21\u786e\u8ba4\u7684\u6846\u4f1a\u9501\u5b9a\u4e3a\u6807\u51c6\u5c3a\u5bf8\u3002"}`}
          </p>
        </section>

        <ol className="workflow-hint" aria-label={"\u64cd\u4f5c\u6b65\u9aa4"}>
          <li>{"\u4e0a\u4f20\u89c6\u9891"}</li>
          <li>{"\u5b9a\u4f4d\u5230\u4e00\u5e27\u6e05\u6670\u753b\u9762"}</li>
          <li>{"\u62d6\u62fd\u6846\u9009\u76ee\u6807\u4eba\u7269\uff0c\u70b9\u51fb\u201c\u786e\u5b9a\u6846\u9009\u201d"}</li>
          <li>{"\u70b9\u51fb\u201c\u9501\u5b9a\u76ee\u6807\u201d"}</li>
          <li>{"\u70b9\u51fb\u201c\u5f00\u59cb\u8ddf\u8e2a\u201d"}</li>
        </ol>

        <div className="button-grid">
          <button disabled={busy} onClick={handleLockTarget}>
            <Crosshair size={17} /> {text.lockTarget}
          </button>
          <button disabled={busy} onClick={handleStartTracking}>
            <Play size={17} /> {text.startTracking}
          </button>
          <button disabled={busy} onClick={handleSaveCorrection}>
            <RefreshCw size={17} /> {text.saveCorrection}
          </button>
          <button disabled={busy} onClick={handleExport}>
            <Download size={17} /> {text.export916}
          </button>
          <button
            disabled={busy}
            onClick={handleAIAnalyze}
            style={{
              gridColumn: "span 1",
              background: "#4f46e5",
              color: "#fff",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              whiteSpace: "nowrap",
              gap: "6px",
              padding: "8px 6px",
            }}
          >
            <Sparkles size={16} /> AI 构图分析
          </button>
          <button
            disabled={busy}
            onClick={() => setAiConfigOpen(true)}
            style={{
              gridColumn: "span 1",
              background: "#334155",
              color: "#fff",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              whiteSpace: "nowrap",
              gap: "6px",
              padding: "8px 6px",
            }}
          >
            <Settings size={16} /> 大模型设置
          </button>
        </div>

        <p className="status-line">{busy ? "\u5904\u7406\u4e2d..." : message}</p>
        {job?.state === "exported" ? (
          <div className="export-info">
            <strong>导出结果</strong>
            <p>{job.message}</p>
            {job.export_path ? <p>文件位置：{job.export_path}</p> : null}
            {job.download_url ? (
              <a href={`http://127.0.0.1:8000${job.download_url}`} target="_blank" rel="noreferrer">
                打开导出文件
              </a>
            ) : null}
          </div>
        ) : null}
      </aside>

      <section className="workspace">
        <div className="viewer-header">
          <div>
            <p className="eyebrow">Preview</p>
            <h2>{job?.source_filename ?? text.waitingVideo}</h2>
          </div>
          <div className="progress-pill">{Math.round((job?.progress ?? 0) * 100)}%</div>
        </div>

        <div
          ref={previewRef}
          className={`video-stage ${pointMode === "box" ? "box-mode" : ""}`}
        >
          <div
            ref={videoLayerRef}
            className="video-layer"
            style={
              {
                aspectRatio: `${frameWidth} / ${frameHeight}`,
                "--video-ratio": `${frameWidth / frameHeight}`,
              } as React.CSSProperties
            }
            onClick={onPreviewClick}
            onMouseDown={onPreviewMouseDown}
            onMouseMove={onPreviewMouseMove}
            onMouseUp={onPreviewMouseUp}
            onMouseLeave={() => {
              if (dragStartRef.current) {
                dragStartRef.current = null;
                setDraftBox(null);
              }
            }}
          >
            {videoUrl ? (
              <>
                <video
                  ref={videoRef}
                  src={videoUrl}
                  controls
                  onLoadedMetadata={() => {
                    if (!videoRef.current) return;
                    setVideoMeta({
                      width: videoRef.current.videoWidth || fallbackFrameWidth,
                      height: videoRef.current.videoHeight || fallbackFrameHeight,
                    });
                  }}
                  onTimeUpdate={onVideoTimeUpdate}
                  onPlay={() => {
                    if (dragStartRef.current || pointMode === "box" || pointMode === "positive" || pointMode === "negative") {
                      if (videoRef.current && !videoRef.current.paused) {
                        videoRef.current.pause();
                      }
                    }
                  }}
                />
                <div
                  className="stage-interaction-mask"
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: "54px",
                    zIndex: 15,
                    cursor: pointMode === "box" ? "crosshair" : pointMode === "positive" ? "copy" : pointMode === "negative" ? "not-allowed" : "default",
                  }}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (videoRef.current && !videoRef.current.paused) {
                      videoRef.current.pause();
                    }
                    onPreviewClick(e);
                  }}
                  onMouseDown={(e) => {
                    e.stopPropagation();
                    if (videoRef.current && !videoRef.current.paused) {
                      videoRef.current.pause();
                    }
                    onPreviewMouseDown(e);
                  }}
                  onMouseMove={(e) => {
                    e.stopPropagation();
                    onPreviewMouseMove(e);
                  }}
                  onMouseUp={(e) => {
                    e.stopPropagation();
                    if (videoRef.current && !videoRef.current.paused) {
                      videoRef.current.pause();
                    }
                    onPreviewMouseUp(e);
                  }}
                />
              </>
            ) : (
              <Film className="empty-icon" size={80} />
            )}
            {currentTrack ? (
              <>
                <div
                  className="crop-guide active-crop"
                  style={{
                    left: `${(currentTrack.crop_box.x / frameWidth) * 100}%`,
                    top: `${(currentTrack.crop_box.y / frameHeight) * 100}%`,
                    width: `${(currentTrack.crop_box.width / frameWidth) * 100}%`,
                    height: `${(currentTrack.crop_box.height / frameHeight) * 100}%`,
                  }}
                  title="9:16 实时竖屏裁剪视窗"
                />
                <span
                  className={`target-box ai-tracked ${currentTrack.suspicious ? "suspicious" : ""}`}
                  style={{
                    left: `${(currentTrack.subject_box.x / frameWidth) * 100}%`,
                    top: `${(currentTrack.subject_box.y / frameHeight) * 100}%`,
                    width: `${(currentTrack.subject_box.width / frameWidth) * 100}%`,
                    height: `${(currentTrack.subject_box.height / frameHeight) * 100}%`,
                  }}
                  title={`AI跟踪 (置信度: ${Math.round(currentTrack.confidence * 100)}%)`}
                />
              </>
            ) : null}
            {currentBox ? (
              <span
                className="target-box"
                style={{
                  left: `${(currentBox.x / frameWidth) * 100}%`,
                  top: `${(currentBox.y / frameHeight) * 100}%`,
                  width: `${(currentBox.width / frameWidth) * 100}%`,
                  height: `${(currentBox.height / frameHeight) * 100}%`,
                }}
                title={text.boxPerson}
              />
            ) : null}
            {draftBox ? (
              <span
                className="target-box draft"
                style={{
                  left: `${(draftBox.x / frameWidth) * 100}%`,
                  top: `${(draftBox.y / frameHeight) * 100}%`,
                  width: `${(draftBox.width / frameWidth) * 100}%`,
                  height: `${(draftBox.height / frameHeight) * 100}%`,
                }}
                title={text.boxPerson}
              />
            ) : null}
            {currentPoints.map((point, index) => (
              <span
                key={`${point.frameIndex}-${point.x}-${point.y}-${index}`}
                className={`target-point ${point.label}`}
                style={{ left: `${(point.x / frameWidth) * 100}%`, top: `${(point.y / frameHeight) * 100}%` }}
                title={point.label === "positive" ? text.positivePoint : text.negativePoint}
              />
            ))}
          </div>
        </div>

        <div className="timeline">
          <div className="timeline-row">
            {Array.from({ length: 36 }).map((_, index) => {
              const frame = Math.round((index / 35) * Math.max(1, job?.frame_count ?? 300));
              return (
                <button
                  key={frame}
                  className={suspiciousSet.has(frame) ? "flagged" : ""}
                  onClick={() => selectFrame(frame)}
                  aria-label={`frame ${frame}`}
                />
              );
            })}
          </div>
          <div className="timeline-meta">
            <span>{`${text.currentFrame}\uff1a${selectedFrame}`}</span>
            <span>{text.redSegments}</span>
          </div>
        </div>

        {aiModalOpen && aiAnalysis ? (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: "rgba(0,0,0,0.75)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 9999,
              padding: "20px",
            }}
          >
            <div
              style={{
                background: "#1e293b",
                border: "1px solid #334155",
                borderRadius: "12px",
                padding: "24px",
                maxWidth: "600px",
                width: "100%",
                color: "#f8fafc",
                boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
              }}
            >
              <h3 style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: 0, fontSize: "18px", color: "#38bdf8" }}>
                <Sparkles size={20} /> AI 大模型多模态帧构图评估 ({aiConfig?.model_name ?? "gpt-4o"})
              </h3>
              <div
                style={{
                  background: "#0f172a",
                  padding: "16px",
                  borderRadius: "8px",
                  lineHeight: "1.6",
                  fontSize: "14px",
                  maxHeight: "300px",
                  overflowY: "auto",
                  margin: "16px 0",
                  whiteSpace: "pre-wrap",
                }}
              >
                {aiAnalysis.analysis}
              </div>
              {aiAnalysis.suggested_box ? (
                <div style={{ background: "#1e3a8a", padding: "12px", borderRadius: "8px", fontSize: "13px", marginBottom: "16px" }}>
                  <strong>🎯 AI 推荐 9:16 竖屏包围框：</strong>
                  {` x: ${Math.round(aiAnalysis.suggested_box.x)}, y: ${Math.round(aiAnalysis.suggested_box.y)}, 宽: ${Math.round(aiAnalysis.suggested_box.width)}, 高: ${Math.round(aiAnalysis.suggested_box.height)}`}
                </div>
              ) : null}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
                <button
                  onClick={() => setAiModalOpen(false)}
                  style={{ background: "#334155", color: "#fff", border: "none", padding: "8px 16px", borderRadius: "6px", cursor: "pointer" }}
                >
                  关闭
                </button>
                {aiAnalysis.suggested_box ? (
                  <button
                    onClick={() => applyAIBox(aiAnalysis.suggested_box!)}
                    style={{ background: "#38bdf8", color: "#0f172a", fontWeight: "bold", border: "none", padding: "8px 16px", borderRadius: "6px", cursor: "pointer" }}
                  >
                    🚀 一键应用 AI 推荐边框并纠偏
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}

        {aiConfigOpen ? (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: "rgba(0,0,0,0.75)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 9999,
              padding: "20px",
            }}
          >
            <div
              style={{
                background: "#1e293b",
                border: "1px solid #334155",
                borderRadius: "12px",
                padding: "24px",
                maxWidth: "520px",
                width: "100%",
                color: "#f8fafc",
                boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
              }}
            >
              <h3 style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: 0, fontSize: "18px", color: "#e2e8f0" }}>
                <Settings size={20} /> 多模态大模型配置 (AI Config)
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "14px", margin: "16px 0" }}>
                <div>
                  <label style={{ display: "block", fontSize: "13px", color: "#94a3b8", marginBottom: "4px" }}>API 密钥 (API Key):</label>
                  <input
                    type="password"
                    value={aiConfig?.api_key ?? ""}
                    onChange={(e) => setAiConfig(aiConfig ? { ...aiConfig, api_key: e.target.value } : null)}
                    placeholder="sk-..."
                    style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #475569", background: "#0f172a", color: "#f8fafc" }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "13px", color: "#94a3b8", marginBottom: "4px" }}>接口请求基址 (Base URL):</label>
                  <input
                    type="text"
                    value={aiConfig?.base_url ?? ""}
                    onChange={(e) => setAiConfig(aiConfig ? { ...aiConfig, base_url: e.target.value } : null)}
                    placeholder="https://api.openai.com/v1"
                    style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #475569", background: "#0f172a", color: "#f8fafc" }}
                  />
                  <span style={{ fontSize: "12px", color: "#64748b" }}>支持任意兼容 OpenAI / Qwen-VL / DeepSeek / 硅基流动的请求接口</span>
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "13px", color: "#94a3b8", marginBottom: "4px" }}>模型名字 (Model Name):</label>
                  <input
                    type="text"
                    value={aiConfig?.model_name ?? ""}
                    onChange={(e) => setAiConfig(aiConfig ? { ...aiConfig, model_name: e.target.value } : null)}
                    placeholder="gpt-4o / qwen-vl-max / deepseek-chat"
                    style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #475569", background: "#0f172a", color: "#f8fafc" }}
                  />
                </div>
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
                <button
                  onClick={() => setAiConfigOpen(false)}
                  style={{ background: "#334155", color: "#fff", border: "none", padding: "8px 16px", borderRadius: "6px", cursor: "pointer" }}
                >
                  取消
                </button>
                <button
                  onClick={async () => {
                    if (aiConfig) {
                      const updated = await updateAIConfig(aiConfig);
                      setAiConfig(updated);
                      setAiConfigOpen(false);
                      setMessage("已保存最新大模型配置（含 API Key 与模型名称）。");
                    }
                  }}
                  style={{ background: "#38bdf8", color: "#0f172a", fontWeight: "bold", border: "none", padding: "8px 16px", borderRadius: "6px", cursor: "pointer" }}
                >
                  保存设置
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </section>
    </main>
  );
}

function Step({ active, title, value }: { active: boolean; title: string; value: string }) {
  return (
    <div className={active ? "step active" : "step"}>
      <span />
      <div>
        <strong>{title}</strong>
        <p>{value}</p>
      </div>
    </div>
  );
}
