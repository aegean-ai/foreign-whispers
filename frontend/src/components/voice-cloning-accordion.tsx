"use client";

import { AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { CircleDotIcon, CircleIcon } from "lucide-react";
import { MicIcon } from "lucide-react";

interface VoiceCloningAccordionProps {
  selected: string[];
  onToggle: (value: string) => void;
}

const METHODS = [
  { value: "xtts", label: "XTTS Speaker Embedding", description: "Clone from reference audio via XTTS v2" },
  { value: "openvoice", label: "OpenVoice", description: "Zero-shot voice cloning" },
];

export function VoiceCloningAccordion({ selected, onToggle }: VoiceCloningAccordionProps) {
  return (
    <AccordionItem value="voice-cloning-methods">
      <AccordionTrigger className="px-3 text-sm">
        <MicIcon className="size-3.5 mr-1.5" />
        Voice Cloning
      </AccordionTrigger>
      <AccordionContent className="px-3 pb-3">
        <div className="flex flex-col gap-2">
          {METHODS.map((m) => (
            <button
              type="button"
              key={m.value}
              className="flex cursor-pointer items-center gap-3 rounded-md border border-border/40 p-2 text-left transition-colors hover:bg-accent/10 data-[checked=true]:border-primary/50 data-[checked=true]:bg-primary/5"
              data-checked={selected.includes(m.value)}
              onClick={() => onToggle(m.value)}
            >
              {selected.includes(m.value) ? (
                <CircleDotIcon className="size-4 shrink-0 text-primary" />
              ) : (
                <CircleIcon className="size-4 shrink-0 text-muted-foreground" />
              )}
              <div>
                <div className="text-sm font-medium">{m.label}</div>
                <div className="text-xs text-muted-foreground">{m.description}</div>
              </div>
            </button>
          ))}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}
