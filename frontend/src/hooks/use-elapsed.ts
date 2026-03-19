"use client";

import { useEffect, useState } from "react";

/**
 * Returns a live elapsed-ms counter that ticks every second while
 * `startedAt` is truthy. Returns `undefined` when inactive.
 */
export function useElapsed(startedAt: number | undefined): number | undefined {
  const [elapsed, setElapsed] = useState<number | undefined>(undefined);

  useEffect(() => {
    if (!startedAt) {
      setElapsed(undefined);
      return;
    }
    setElapsed(Date.now() - startedAt);
    const id = setInterval(() => setElapsed(Date.now() - startedAt), 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  return elapsed;
}
