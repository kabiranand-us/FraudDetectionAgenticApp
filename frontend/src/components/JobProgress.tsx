import { useEffect, useState } from "react";
import { Spinner } from "./bits";
import type { Job } from "../types";

/** What the agents are doing, and how long it has taken so far. */
export default function JobProgress({ job, fallback }: { job: Job; fallback: string }) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(t);
  }, []);
  const seconds = job.started_at ? Math.max(0, Math.round(now - job.started_at)) : 0;
  const elapsed = seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return (
    <div className="job">
      <Spinner />
      <span>
        <strong>{job.stage || fallback}</strong>
        {job.step && <span className="muted"> · {job.step}</span>}
        <span className="muted"> · {elapsed}</span>
      </span>
    </div>
  );
}
