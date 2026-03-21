"use client";

import { AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { CircleDotIcon, CircleIcon, Volume2Icon } from "lucide-react";

interface DubbingMethodAccordionProps {
  selected: string[];
  onToggle: (value: string) => void;
}

const METHODS = [
  { value: "baseline", label: "Baseline", description: "No temporal alignment" },
  { value: "aligned", label: "Aligned", description: "Syllable-based stretch to match original timing" },
];

export function DubbingMethodAccordion({ selected, onToggle }: DubbingMethodAccordionProps) {
  return (
    <AccordionItem value="dubbing-method">
      <AccordionTrigger className="px-3 text-sm">
        <Volume2Icon className="size-3.5 mr-1.5" />
        Alignment
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
