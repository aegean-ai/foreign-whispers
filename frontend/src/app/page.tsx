import { PipelinePage } from "@/components/pipeline-page";
import type { Video } from "@/lib/types";

const API_URL = process.env.API_URL || "http://localhost:8080";

export default async function Home() {
  const res = await fetch(`${API_URL}/api/videos`, { cache: "no-store" });
  const videos: Video[] = res.ok ? await res.json() : [];

  return <PipelinePage videos={videos} />;
}
