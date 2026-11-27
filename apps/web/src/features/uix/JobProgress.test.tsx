// CT-FN-UIX-03: job progress polls FN-JOB-03 and refreshes on completion.
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createJudeClient } from "@jude/contracts";

import { t } from "../../i18n";
import { JobProgress } from "./JobProgress";
import type { JobStatus } from "./jobStatus";

const JOB = "6f1c0a52-8d0e-4c1f-9a51-0f6f8f0b1a11";

function job(over: Partial<JobStatus> = {}): JobStatus {
  return {
    job_id: JOB,
    type: "regenerate.v1",
    status: "queued",
    attempts: 0,
    progress: null,
    result: null,
    error_code: null,
    message_ru: null,
    step: null,
    correlation_id: "c",
    created_at: "2026-11-27T09:00:00Z",
    finished_at: null,
    ...over,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function setup(answers: Array<() => Response>, onDone = vi.fn()) {
  let i = 0;
  const fetchMock = vi.fn(async (_r: Request) => answers[Math.min(i++, answers.length - 1)]!());
  vi.stubGlobal("fetch", fetchMock);
  render(
    <JobProgress
      client={createJudeClient("http://jude.test")}
      jobId={JOB}
      caseId="c-1"
      intervalMs={1000}
      onDone={onDone}
    />,
  );
  return { fetchMock, onDone };
}

async function tick(ms = 1000) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("JobProgress", () => {
  it("polls until the job ends, shows progress, then stops and calls onDone once", async () => {
    const done = job({ status: "succeeded", attempts: 1, finished_at: "2026-11-27T09:00:05Z" });
    const { fetchMock, onDone } = setup([
      () => json(job()),
      () => json(job({ status: "running", attempts: 1, progress: 0.4 })),
      () => json(done),
    ]);
    await tick(0);
    expect(screen.getByText(t("job.queued"))).toBeTruthy();
    const request = fetchMock.mock.calls[0]![0];
    expect(new URL(request.url).pathname).toBe(`/api/v1/jobs/${JOB}`);
    await tick();
    expect(screen.getByText(t("job.running"))).toBeTruthy();
    const bar = screen.getByLabelText(t("job.progress")) as HTMLProgressElement;
    expect(bar.value).toBeCloseTo(0.4);
    await tick();
    expect(screen.getByText(t("job.succeeded"))).toBeTruthy();
    expect(onDone).toHaveBeenCalledExactlyOnceWith(done);
    await tick(5000);
    expect(fetchMock).toHaveBeenCalledTimes(3); // no poll after the end
  });

  it("shows a failed job's message with a link to the step that resolves it", async () => {
    const failed = job({
      status: "failed",
      error_code: "SELF_INTERSECTION_CREATED",
      message_ru: "Операция создаёт самопересечение.",
      step: "S8",
    });
    const { onDone } = setup([() => json(failed)]);
    await tick(0);
    expect(screen.getByRole("alert").textContent).toContain("Операция создаёт самопересечение.");
    expect(screen.getByRole("link").getAttribute("href")).toBe("/cases/c-1/design");
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("keeps polling through an unreachable server and recovers", async () => {
    const { fetchMock } = setup([
      () => json(job({ status: "running", attempts: 1 })),
      () => {
        throw new TypeError("network");
      },
      () => json(job({ status: "succeeded", attempts: 1 })),
    ]);
    await tick(0);
    await tick();
    expect(screen.getByRole("status").textContent).toBe(t("job.unavailable"));
    expect(screen.getByText(t("job.running"))).toBeTruthy(); // last known status stays
    await tick();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByText(t("job.succeeded"))).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("stops on 404 and renders the refusal as a gate list", async () => {
    const { fetchMock, onDone } = setup([
      () =>
        json(
          {
            error: "NOT_FOUND",
            http_status: 404,
            message_ru: "Объект не найден.",
            step: "CURRENT",
            gates: [],
            correlation_id: "c",
          },
          404,
        ),
    ]);
    await tick(0);
    expect(screen.getByRole("alert").textContent).toContain("Объект не найден.");
    await tick(5000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(onDone).not.toHaveBeenCalled();
  });

  it("ignores an answer that arrives after unmount and schedules nothing", async () => {
    let answer: (r: Response) => void = () => {};
    const fetchMock = vi.fn(() => new Promise<Response>((ok) => (answer = ok)));
    vi.stubGlobal("fetch", fetchMock);
    render(<JobProgress client={createJudeClient("http://jude.test")} jobId={JOB} />);
    await tick(0);
    cleanup();
    await act(async () => answer(json(job({ status: "running", attempts: 1 }))));
    await tick(5000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("stops polling when unmounted", async () => {
    const { fetchMock } = setup([() => json(job({ status: "running", attempts: 1 }))]);
    await tick(0);
    cleanup();
    await tick(5000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
