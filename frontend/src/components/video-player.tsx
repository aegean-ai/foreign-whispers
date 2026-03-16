"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface VideoPlayerProps {
  src: string;
  title?: string;
}

export function VideoPlayer({ src, title = "Dubbed Video" }: VideoPlayerProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <video controls className="w-full rounded-md" src={src}>
          Your browser does not support the video element.
        </video>
      </CardContent>
    </Card>
  );
}
