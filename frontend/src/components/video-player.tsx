"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface VideoPlayerProps {
  src: string;
  captionsSrc?: string;
  captionsLang?: string;
  captionsLabel?: string;
  title?: string;
}

export function VideoPlayer({
  src,
  captionsSrc,
  captionsLang = "es",
  captionsLabel = "Spanish",
  title = "Dubbed Video",
}: VideoPlayerProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <video controls className="w-full rounded-md" src={src} crossOrigin="anonymous">
          {captionsSrc && (
            <track
              kind="subtitles"
              src={captionsSrc}
              srcLang={captionsLang}
              label={captionsLabel}
              default
            />
          )}
        </video>
      </CardContent>
    </Card>
  );
}
