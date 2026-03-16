"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface AudioPlayerProps {
  src: string;
  title?: string;
}

export function AudioPlayer({ src, title = "Synthesized Audio" }: AudioPlayerProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <audio controls className="w-full" src={src}>
          Your browser does not support the audio element.
        </audio>
      </CardContent>
    </Card>
  );
}
