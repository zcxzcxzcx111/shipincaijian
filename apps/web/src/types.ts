export type Point = {
  x: number;
  y: number;
  label: "positive" | "negative";
};

export type Box = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type TrackingFrame = {
  frame_index: number;
  subject_box: Box;
  crop_box: Box;
  confidence: number;
  suspicious: boolean;
};

export type JobStatus = {
  id: string;
  state: "created" | "target_selected" | "tracking" | "tracked" | "exporting" | "exported" | "failed";
  progress: number;
  message: string;
  source_filename: string;
  proxy_url?: string | null;
  download_url?: string | null;
  export_path?: string | null;
  suspicious_frames: number[];
  frame_count: number;
  width: number;
  height: number;
  tracking_frames?: TrackingFrame[] | null;
};

export type AIConfig = {
  api_key: string;
  base_url: string;
  model_name: string;
  enabled: boolean;
};

export type AIAnalyzeResponse = {
  success: boolean;
  analysis: string;
  suggested_box?: Box | null;
  frame_width?: number | null;
  frame_height?: number | null;
  fallback_reason?: string | null;
};

