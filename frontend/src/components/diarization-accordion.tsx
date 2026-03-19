"use client";

import { AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { Checkbox } from "@/components/ui/checkbox";
import { UsersIcon } from "lucide-react";

interface DiarizationAccordionProps {
  selected: string[];
  onToggle: (value: string) => void;
}

const METHODS = [
  { value: "pyannote", label: "pyannote", description: "Speaker diarization via pyannote.audio" },
  { value: "whisper-based", label: "Whisper-based", description: "Speaker detection from Whisper timestamps" },
];

export function DiarizationAccordion({ selected, onToggle }: DiarizationAccordionProps) {
  return (
    <AccordionItem value="diarization-methods">
      <AccordionTrigger className="px-3 text-sm">
        <UsersIcon className="size-3.5 mr-1.5" />
        Diarization
      </AccordionTrigger>
      <AccordionContent className="px-3 pb-3">
        <div className="flex flex-col gap-2">
          {METHODS.map((m) => (
            <label
              key={m.value}
              className="flex cursor-pointer items-center gap-3 rounded-md border border-border/40 p-2 transition-colors hover:bg-accent/10 data-[checked=true]:border-primary/50 data-[checked=true]:bg-primary/5"
              data-checked={selected.includes(m.value)}
            >
              <Checkbox
                checked={selected.includes(m.value)}
                onCheckedChange={() => onToggle(m.value)}
              />
              <div>
                <div className="text-sm font-medium">{m.label}</div>
                <div className="text-xs text-muted-foreground">{m.description}</div>
              </div>
            </label>
          ))}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}
