import type {
  DownloadResponse,
  TranscribeResponse,
  TranslateResponse,
  TTSResponse,
  StitchResponse,
} from "./types";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new ApiError(res.status, text);
  }
  return res.json();
}

export async function downloadVideo(url: string): Promise<DownloadResponse> {
  return fetchJson<DownloadResponse>("/api/download", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function transcribeVideo(videoId: string): Promise<TranscribeResponse> {
  return fetchJson<TranscribeResponse>(`/api/transcribe/${videoId}`, {
    method: "POST",
  });
}

export async function translateVideo(
  videoId: string,
  targetLanguage = "es"
): Promise<TranslateResponse> {
  return fetchJson<TranslateResponse>(
    `/api/translate/${videoId}?target_language=${targetLanguage}`,
    { method: "POST" }
  );
}

export async function synthesizeSpeech(
  videoId: string,
  mode: "baseline" | "aligned" = "baseline"
): Promise<TTSResponse> {
  return fetchJson<TTSResponse>(`/api/tts/${videoId}?mode=${mode}`, {
    method: "POST",
  });
}

export async function stitchVideo(
  videoId: string,
  mode: "baseline" | "aligned" = "baseline"
): Promise<StitchResponse> {
  return fetchJson<StitchResponse>(`/api/stitch/${videoId}?mode=${mode}`, {
    method: "POST",
  });
}

export function getVideoUrl(videoId: string, mode: "baseline" | "aligned" = "baseline"): string {
  return `/api/video/${videoId}?mode=${mode}`;
}

export function getOriginalVideoUrl(videoId: string): string {
  return `/api/video/${videoId}/original`;
}

export function getAudioUrl(videoId: string, mode: "baseline" | "aligned" = "baseline"): string {
  return `/api/audio/${videoId}?mode=${mode}`;
}

export function getCaptionsUrl(videoId: string): string {
  return `/api/captions/${videoId}`;
}

export function getOriginalCaptionsUrl(videoId: string): string {
  return `/api/captions/${videoId}/original`;
}
