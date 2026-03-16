"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatTime } from "@/lib/utils";
import type { TranscribeSegment } from "@/lib/types";

interface TranslationViewProps {
  englishSegments: TranscribeSegment[];
  spanishSegments: TranscribeSegment[];
}

export function TranslationView({
  englishSegments,
  spanishSegments,
}: TranslationViewProps) {
  return (
    <Tabs defaultValue="side-by-side">
      <TabsList>
        <TabsTrigger value="side-by-side">Side by Side</TabsTrigger>
        <TabsTrigger value="english">English</TabsTrigger>
        <TabsTrigger value="spanish">Spanish</TabsTrigger>
      </TabsList>

      <TabsContent value="side-by-side">
        <ScrollArea className="h-[500px]">
          <div className="flex flex-col gap-3 pr-4">
            {englishSegments.map((en, i) => {
              const es = spanishSegments[i];
              return (
                <div key={i} className="grid grid-cols-[50px_1fr_1fr] gap-3">
                  <span className="font-mono text-xs text-primary/70">
                    {formatTime(en.start)}
                  </span>
                  <p className="text-sm text-foreground">{en.text}</p>
                  <p className="text-sm text-amber-200/90">{es?.text ?? ""}</p>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="english">
        <ScrollArea className="h-[500px]">
          <div className="flex flex-col gap-2 pr-4">
            {englishSegments.map((seg, i) => (
              <div key={i} className="flex gap-3">
                <span className="font-mono text-xs text-primary/70">
                  {formatTime(seg.start)}
                </span>
                <p className="text-sm">{seg.text}</p>
              </div>
            ))}
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="spanish">
        <ScrollArea className="h-[500px]">
          <div className="flex flex-col gap-2 pr-4">
            {spanishSegments.map((seg, i) => (
              <div key={i} className="flex gap-3">
                <span className="font-mono text-xs text-primary/70">
                  {formatTime(seg.start)}
                </span>
                <p className="text-sm text-amber-200/90">{seg.text}</p>
              </div>
            ))}
          </div>
        </ScrollArea>
      </TabsContent>
    </Tabs>
  );
}
