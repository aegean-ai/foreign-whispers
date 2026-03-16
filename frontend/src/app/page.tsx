import { readFile } from "fs/promises";
import { join } from "path";
import { PipelinePage } from "@/components/pipeline-page";
import type { Video } from "@/lib/types";

export default async function Home() {
  const data = await readFile(
    join(process.cwd(), "public", "videos.json"),
    "utf-8"
  );
  const videos: Video[] = JSON.parse(data);

  return <PipelinePage videos={videos} />;
}
