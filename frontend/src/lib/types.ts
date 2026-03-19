export interface Video {
  id: string;
  title: string;
  url: string;
}

export interface CaptionSegment {
  start: number;
  end: number;
  text: string;
  duration?: number;
}

export interface DownloadResponse {
  video_id: string;
  title: string;
  caption_segments: CaptionSegment[];
}

export interface TranscribeSegment {
  id?: number;
  start: number;
  end: number;
  text: string;
}

export interface TranscribeResponse {
  video_id: string;
  language: string;
  text: string;
  segments: TranscribeSegment[];
}

export interface TranslateResponse {
  video_id: string;
  target_language: string;
  text: string;
  segments: TranscribeSegment[];
}

export interface TTSResponse {
  video_id: string;
  audio_path: string;
}

export interface StitchResponse {
  video_id: string;
  video_path: string;
}

export type PipelineStage = "download" | "transcribe" | "translate" | "tts" | "stitch";
export type StageStatus = "pending" | "active" | "complete" | "error";

export interface StageState {
  status: StageStatus;
  result?: unknown;
  error?: string;
  duration_ms?: number;
  started_at?: number;
}

export interface PipelineState {
  status: "idle" | "running" | "complete" | "error";
  stages: Record<PipelineStage, StageState>;
  selectedStage: PipelineStage;
  videoId?: string;
  variants: VideoVariant[];
  activeVariantId?: string;
}

export interface StudioSettings {
  dubbing: string[];
  diarization: string[];
  voiceCloning: string[];
}

export interface VideoVariant {
  id: string;
  sourceVideoId: string;
  label: string;
  settings: StudioSettings;
  status: "complete" | "processing" | "error";
}

export const DEFAULT_STUDIO_SETTINGS: StudioSettings = {
  dubbing: ["baseline"],
  diarization: [],
  voiceCloning: [],
};
