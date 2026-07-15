import type { AIAnalyzeResponse, AIConfig, Box, JobStatus, Point } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function createJob(file: File): Promise<JobStatus> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/api/jobs`, {
    method: "POST",
    body: form,
  });
  return parseJson<JobStatus>(response);
}

export async function submitTarget(jobId: string, frameIndex: number, points: Point[], box?: Box): Promise<JobStatus> {
  const response = await fetch(`${API_BASE}/api/jobs/${jobId}/target`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ frame_index: frameIndex, points, box }),
  });
  return parseJson<JobStatus>(response);
}

export async function startTracking(jobId: string): Promise<JobStatus> {
  const response = await fetch(`${API_BASE}/api/jobs/${jobId}/track`, { method: "POST" });
  return parseJson<JobStatus>(response);
}

export async function submitCorrection(jobId: string, frameIndex: number, box: Box): Promise<JobStatus> {
  const response = await fetch(`${API_BASE}/api/jobs/${jobId}/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ corrections: [{ frame_index: frameIndex, box }] }),
  });
  return parseJson<JobStatus>(response);
}

export async function exportJob(jobId: string): Promise<JobStatus> {
  const response = await fetch(`${API_BASE}/api/jobs/${jobId}/export`, { method: "POST" });
  return parseJson<JobStatus>(response);
}

export async function getStatus(jobId: string): Promise<JobStatus> {
  const response = await fetch(`${API_BASE}/api/jobs/${jobId}/status`);
  return parseJson<JobStatus>(response);
}

export async function getAIConfig(): Promise<AIConfig> {
  const response = await fetch(`${API_BASE}/api/ai/config`);
  return parseJson<AIConfig>(response);
}

export async function updateAIConfig(config: Partial<AIConfig>): Promise<AIConfig> {
  const response = await fetch(`${API_BASE}/api/ai/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  return parseJson<AIConfig>(response);
}

export async function analyzeFrameWithAI(jobId: string, frameIndex: number, currentBox?: Box | null): Promise<AIAnalyzeResponse> {
  const response = await fetch(`${API_BASE}/api/jobs/${jobId}/ai-analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ frame_index: frameIndex, current_box: currentBox }),
  });
  return parseJson<AIAnalyzeResponse>(response);
}


