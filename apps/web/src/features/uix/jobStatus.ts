// FN-UIX-03 step 2: poll job status (FN-JOB-03) and refresh views on completion (TSK-UIX-03-U).
//
// - One request at a time: the next poll is scheduled only after the previous answer, so a slow
//   server never sees overlapping polls.
// - The poll stops when the job ends (succeeded / failed) and `onDone` fires exactly once, so
//   the screen can reload the objects the job produced.
// - An unreachable server or a refusal does not end the poll: the job keeps running on the
//   worker, and the next answer replaces the problem. A 404 (unknown, or not visible) is final.
// - The interval is a UI refresh rate, not a clinical or production value.
// - Follow another job by remounting with `key={jobId}`, so no stale status carries over.
import { useEffect, useRef, useState } from "react";

import type { ErrorResponse, JudeClient, components } from "@jude/contracts";

export type JobStatus = components["schemas"]["JobStatusResponse"];

export type JobView =
  | { kind: "loading" }
  | { kind: "status"; job: JobStatus }
  | { kind: "unavailable"; last: JobStatus | null }
  | { kind: "refused"; error: ErrorResponse; last: JobStatus | null };

export const DEFAULT_POLL_MS = 1000;

export function isFinal(job: JobStatus): boolean {
  return job.status === "succeeded" || job.status === "failed";
}

export type PollAnswer =
  | { kind: "status"; job: JobStatus }
  | { kind: "refused"; error: ErrorResponse }
  | { kind: "unavailable" };

export async function fetchJobStatus(client: JudeClient, jobId: string): Promise<PollAnswer> {
  try {
    const { data, error } = await client.GET("/api/v1/jobs/{job_id}", {
      params: { path: { job_id: jobId } },
    });
    if (data) return { kind: "status", job: data };
    if (error && typeof error === "object" && "error" in error) {
      return { kind: "refused", error: error as ErrorResponse };
    }
  } catch {
    // network failure or a non-JSON answer from a proxy
  }
  return { kind: "unavailable" };
}

type Options = {
  intervalMs?: number;
  onDone?: (job: JobStatus) => void;
};

export function useJobStatus(client: JudeClient, jobId: string, options: Options = {}): JobView {
  const { intervalMs = DEFAULT_POLL_MS } = options;
  const [view, setView] = useState<JobView>({ kind: "loading" });
  const onDone = useRef(options.onDone);
  useEffect(() => {
    onDone.current = options.onDone;
  });

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let last: JobStatus | null = null;

    async function poll() {
      const answer = await fetchJobStatus(client, jobId);
      if (stopped) return;
      if (answer.kind === "status") {
        last = answer.job;
        setView({ kind: "status", job: answer.job });
        if (isFinal(answer.job)) {
          onDone.current?.(answer.job);
          return;
        }
      } else if (answer.kind === "refused") {
        setView({ kind: "refused", error: answer.error, last });
        if (answer.error.http_status === 404) return;
      } else {
        setView({ kind: "unavailable", last });
      }
      timer = setTimeout(poll, intervalMs);
    }

    void poll();
    return () => {
      stopped = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [client, jobId, intervalMs]);

  return view;
}
