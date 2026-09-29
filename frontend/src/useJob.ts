import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Job } from "./types";

const failed = (detail: string, jobId = ""): Job => ({
  job_id: jobId, state: "failed", kind: "", target: "", detail,
  stage: "Failed", step: "", started_at: 0,
});

/** Starts a long agent job and polls it until it finishes. */
export function useJob(onDone: () => void) {
  const [job, setJob] = useState<Job | null>(null);
  const timer = useRef<number | null>(null);
  const done = useRef(onDone);
  done.current = onDone;

  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);

  const poll = useCallback((jobId: string) => {
    timer.current = window.setTimeout(async () => {
      try {
        const next = await api.job(jobId);
        setJob(next);
        if (next.state === "running") poll(jobId);
        else if (next.state === "done") done.current();
      } catch (e) {
        setJob(failed((e as Error).message, jobId));
      }
    }, 3000);
  }, []);

  const start = useCallback(
    async (starter: () => Promise<Job>) => {
      try {
        const started = await starter();
        setJob(started);
        poll(started.job_id);
      } catch (e) {
        setJob(failed((e as Error).message));
      }
    },
    [poll],
  );

  return { job, start, running: job?.state === "running", clear: () => setJob(null) };
}
