"use client";

// FN-UIX-03 job progress (TSK-UIX-03-U): status, progress while running, and on failure the
// server's Russian message with a link to the step that resolves the code (FN-JOB-03 `step`).
import type { JudeClient } from "@jude/contracts";

import { t, type MessageKey } from "../../i18n";
import { GateList, StepLink } from "./GateList";
import { type JobStatus, useJobStatus } from "./jobStatus";
import { stepPath } from "./steps";

type Props = {
  client: JudeClient;
  jobId: string;
  caseId?: string | null;
  intervalMs?: number;
  onDone?: (job: JobStatus) => void;
};

const STATUS_LABEL: Record<JobStatus["status"], MessageKey> = {
  queued: "job.queued",
  running: "job.running",
  succeeded: "job.succeeded",
  failed: "job.failed",
};

export function JobProgress({ client, jobId, caseId = null, intervalMs, onDone }: Props) {
  const view = useJobStatus(client, jobId, { intervalMs, onDone });
  if (view.kind === "loading") return <p aria-busy="true">{t("job.queued")}</p>;
  if (view.kind === "refused") return <GateList error={view.error} caseId={caseId} />;
  const job = view.kind === "status" ? view.job : view.last;
  return (
    <div data-job={jobId}>
      {job !== null && <JobLine job={job} caseId={caseId} />}
      {view.kind === "unavailable" && <p role="status">{t("job.unavailable")}</p>}
    </div>
  );
}

function JobLine({ job, caseId }: { job: JobStatus; caseId: string | null }) {
  const href = job.step ? stepPath(job.step, caseId) : null;
  return (
    <div data-status={job.status}>
      <p>{t(STATUS_LABEL[job.status])}</p>
      {job.status === "running" && job.progress !== null && (
        <progress aria-label={t("job.progress")} max={1} value={job.progress} />
      )}
      {job.status === "failed" && job.message_ru !== null && (
        <div role="alert">
          <p>{job.message_ru}</p>
          {href !== null && job.step && <StepLink href={href} step={job.step} />}
        </div>
      )}
    </div>
  );
}
