"use client";

import { useCallback, useReducer } from "react";
import type {
  PipelineStage,
  PipelineState,
  StageState,
  Video,
} from "@/lib/types";
import {
  downloadVideo,
  transcribeVideo,
  translateVideo,
  synthesizeSpeech,
  stitchVideo,
} from "@/lib/api";

const STAGES: PipelineStage[] = [
  "download",
  "transcribe",
  "translate",
  "tts",
  "stitch",
];

function initialStages(): Record<PipelineStage, StageState> {
  return Object.fromEntries(
    STAGES.map((s) => [s, { status: "pending" as const }])
  ) as Record<PipelineStage, StageState>;
}

const INITIAL_STATE: PipelineState = {
  status: "idle",
  stages: initialStages(),
  selectedStage: "download",
  isDemo: false,
};

type Action =
  | { type: "START"; videoId: string }
  | { type: "STAGE_ACTIVE"; stage: PipelineStage }
  | { type: "STAGE_COMPLETE"; stage: PipelineStage; result: unknown; duration_ms: number }
  | { type: "STAGE_ERROR"; stage: PipelineStage; error: string }
  | { type: "SELECT_STAGE"; stage: PipelineStage }
  | { type: "PIPELINE_COMPLETE" }
  | { type: "RESET" }
  | { type: "DEMO_COMPLETE"; results: Record<PipelineStage, unknown> };

function reducer(state: PipelineState, action: Action): PipelineState {
  switch (action.type) {
    case "RESET":
      return INITIAL_STATE;

    case "START":
      return {
        ...state,
        status: "running",
        videoId: action.videoId,
        stages: initialStages(),
        selectedStage: "download",
        isDemo: false,
      };

    case "STAGE_ACTIVE":
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: { status: "active" },
        },
        selectedStage: action.stage,
      };

    case "STAGE_COMPLETE":
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: {
            status: "complete",
            result: action.result,
            duration_ms: action.duration_ms,
          },
        },
        selectedStage: action.stage,
      };

    case "STAGE_ERROR":
      return {
        ...state,
        status: "error",
        stages: {
          ...state.stages,
          [action.stage]: { status: "error", error: action.error },
        },
        selectedStage: action.stage,
      };

    case "PIPELINE_COMPLETE":
      return { ...state, status: "complete", selectedStage: "stitch" };

    case "SELECT_STAGE":
      return { ...state, selectedStage: action.stage };

    case "DEMO_COMPLETE": {
      const stages = {} as Record<PipelineStage, StageState>;
      for (const s of STAGES) {
        stages[s] = { status: "complete", result: action.results[s], duration_ms: 0 };
      }
      return {
        ...state,
        status: "complete",
        stages,
        selectedStage: "stitch",
        isDemo: true,
      };
    }

    default:
      return state;
  }
}

export function usePipeline() {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);

  const selectStage = useCallback(
    (stage: PipelineStage) => dispatch({ type: "SELECT_STAGE", stage }),
    []
  );

  const loadDemo = useCallback(async (video: Video) => {
    if (!video.demo_assets) return;
    const assets = video.demo_assets;
    const [enRes, esRes] = await Promise.all([
      fetch(assets.transcript_en).then((r) => r.json()),
      fetch(assets.transcript_es).then((r) => r.json()),
    ]);
    dispatch({
      type: "DEMO_COMPLETE",
      results: {
        download: { video_id: video.id, title: video.title, caption_segments: [] },
        transcribe: enRes,
        translate: esRes,
        tts: { video_id: video.id, audio_path: assets.audio },
        stitch: { video_id: video.id, video_path: assets.video },
      },
    });
  }, []);

  const runPipeline = useCallback(async (video: Video) => {
    dispatch({ type: "START", videoId: video.id });

    const run = async <T,>(
      stage: PipelineStage,
      fn: () => Promise<T>
    ): Promise<T> => {
      dispatch({ type: "STAGE_ACTIVE", stage });
      const t0 = performance.now();
      try {
        const result = await fn();
        dispatch({
          type: "STAGE_COMPLETE",
          stage,
          result,
          duration_ms: Math.round(performance.now() - t0),
        });
        return result;
      } catch (err) {
        dispatch({
          type: "STAGE_ERROR",
          stage,
          error: err instanceof Error ? err.message : String(err),
        });
        throw err;
      }
    };

    try {
      const dl = await run("download", () => downloadVideo(video.url));
      await run("transcribe", () => transcribeVideo(dl.video_id));
      await run("translate", () => translateVideo(dl.video_id, "es"));
      await run("tts", () => synthesizeSpeech(dl.video_id));
      await run("stitch", () => stitchVideo(dl.video_id));
      dispatch({ type: "PIPELINE_COMPLETE" });
    } catch {
      // Error already dispatched in run()
    }
  }, []);

  const reset = useCallback(() => dispatch({ type: "RESET" }), []);

  return { state, runPipeline, loadDemo, selectStage, reset };
}
