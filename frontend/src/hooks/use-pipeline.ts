"use client";

import { useCallback, useReducer } from "react";
import type {
  PipelineStage,
  PipelineState,
  StageState,
  StudioSettings,
  Video,
  VideoVariant,
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
  variants: [],
};

function makeVariantLabel(settings: StudioSettings): string {
  const parts = [
    ...settings.dubbing.map((d) => d.charAt(0).toUpperCase() + d.slice(1)),
    ...settings.diarization,
    ...settings.voiceCloning,
  ];
  return parts.length > 0 ? parts.join(" + ") : "Default";
}

function makeVariantId(videoId: string, settings: StudioSettings): string {
  const key = [
    ...[...settings.dubbing].sort(),
    ...[...settings.diarization].sort(),
    ...[...settings.voiceCloning].sort(),
  ].join("_");
  return `${videoId}_${key || "default"}`;
}

type Action =
  | { type: "START"; videoId: string; settings: StudioSettings }
  | { type: "STAGE_ACTIVE"; stage: PipelineStage }
  | { type: "STAGE_COMPLETE"; stage: PipelineStage; result: unknown; duration_ms: number }
  | { type: "STAGE_ERROR"; stage: PipelineStage; error: string }
  | { type: "SELECT_STAGE"; stage: PipelineStage }
  | { type: "PIPELINE_COMPLETE" }
  | { type: "SELECT_VARIANT"; variantId: string }
  | { type: "RESET" };

function reducer(state: PipelineState, action: Action): PipelineState {
  switch (action.type) {
    case "RESET":
      return INITIAL_STATE;

    case "START": {
      const variantId = makeVariantId(action.videoId, action.settings);
      const variant: VideoVariant = {
        id: variantId,
        sourceVideoId: action.videoId,
        label: makeVariantLabel(action.settings),
        settings: action.settings,
        status: "processing",
      };
      return {
        ...state,
        status: "running",
        videoId: action.videoId,
        stages: initialStages(),
        selectedStage: "download",
        variants: [
          ...state.variants.filter((v) => v.id !== variantId),
          variant,
        ],
        activeVariantId: variantId,
      };
    }

    case "STAGE_ACTIVE":
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: { status: "active", started_at: Date.now() },
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
        variants: state.variants.map((v) =>
          v.id === state.activeVariantId ? { ...v, status: "error" as const } : v
        ),
      };

    case "PIPELINE_COMPLETE":
      return {
        ...state,
        status: "complete",
        selectedStage: "stitch",
        variants: state.variants.map((v) =>
          v.id === state.activeVariantId ? { ...v, status: "complete" as const } : v
        ),
      };

    case "SELECT_STAGE":
      return { ...state, selectedStage: action.stage };

    case "SELECT_VARIANT":
      return { ...state, activeVariantId: action.variantId };

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

  const selectVariant = useCallback(
    (variantId: string) => dispatch({ type: "SELECT_VARIANT", variantId }),
    []
  );

  const runPipeline = useCallback(async (video: Video, settings: StudioSettings) => {
    dispatch({ type: "START", videoId: video.id, settings });

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
      await run("tts", () => synthesizeSpeech(dl.video_id, settings));
      await run("stitch", () => stitchVideo(dl.video_id));
      dispatch({ type: "PIPELINE_COMPLETE" });
    } catch {
      // Error already dispatched in run()
    }
  }, []);

  const reset = useCallback(() => dispatch({ type: "RESET" }), []);

  return { state, runPipeline, selectStage, selectVariant, reset };
}
