"use client";

import { Accordion } from "@/components/ui/accordion";
import { DubbingMethodAccordion } from "./dubbing-method-accordion";
import { DiarizationAccordion } from "./diarization-accordion";
import { VoiceCloningAccordion } from "./voice-cloning-accordion";
import { TranscriptView } from "./transcript-view";
import { TranslationView } from "./translation-view";
import { AudioPlayer } from "./audio-player";
import { AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { SidebarGroup } from "@/components/ui/sidebar";
import type { StudioSettings, PipelineState, TranscribeResponse, TranslateResponse } from "@/lib/types";
import { getAudioUrl } from "@/lib/api";

interface ControlPanelProps {
  settings: StudioSettings;
  onToggleSetting: (group: keyof StudioSettings, value: string) => void;
  pipelineState: PipelineState;
}

export function ControlPanel({
  settings,
  onToggleSetting,
  pipelineState,
}: ControlPanelProps) {
  const transcribeResult = pipelineState.stages.transcribe.result as TranscribeResponse | undefined;
  const translateResult = pipelineState.stages.translate.result as TranslateResponse | undefined;
  const ttsComplete = pipelineState.stages.tts.status === "complete";

  return (
    <SidebarGroup>
      <Accordion multiple defaultValue={["dubbing-method"]}>
        <DubbingMethodAccordion
          selected={settings.dubbing}
          onToggle={(v) => onToggleSetting("dubbing", v)}
        />
        <DiarizationAccordion
          selected={settings.diarization}
          onToggle={(v) => onToggleSetting("diarization", v)}
        />
        <VoiceCloningAccordion
          selected={settings.voiceCloning}
          onToggle={(v) => onToggleSetting("voiceCloning", v)}
        />

        <AccordionItem value="metrics">
          <AccordionTrigger className="px-3 text-sm text-muted-foreground italic" disabled>
            Metrics
            <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-[10px] not-italic">Soon</span>
          </AccordionTrigger>
        </AccordionItem>

        {transcribeResult && (
          <AccordionItem value="transcript">
            <AccordionTrigger className="px-3 text-sm">Transcript</AccordionTrigger>
            <AccordionContent className="px-3 pb-3">
              <TranscriptView segments={transcribeResult.segments} />
            </AccordionContent>
          </AccordionItem>
        )}

        {translateResult && transcribeResult && (
          <AccordionItem value="translation">
            <AccordionTrigger className="px-3 text-sm">Translation</AccordionTrigger>
            <AccordionContent className="px-3 pb-3">
              <TranslationView
                englishSegments={transcribeResult.segments}
                spanishSegments={translateResult.segments}
              />
            </AccordionContent>
          </AccordionItem>
        )}

        {ttsComplete && pipelineState.videoId && (
          <AccordionItem value="audio">
            <AccordionTrigger className="px-3 text-sm">Audio</AccordionTrigger>
            <AccordionContent className="px-3 pb-3">
              <AudioPlayer src={getAudioUrl(pipelineState.videoId)} />
            </AccordionContent>
          </AccordionItem>
        )}
      </Accordion>
    </SidebarGroup>
  );
}
