// CT-FN-UIX-03: gate list and target steps. Completion criterion: each gate code has a resource
// string and a target step (the server sends both; the client has a label and a route for
// every target).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ErrorResponse } from "@jude/contracts";

import { t } from "../../i18n";
import ru from "../../messages/ru.json";
import { GateList } from "./GateList";
import { STEP_LABEL, type StepTarget, gatePath, stepPath } from "./steps";

const API = resolve(__dirname, "../../../../../services/api/src/jude_api");
const readJson = (p: string) => JSON.parse(readFileSync(resolve(API, p), "utf-8"));
const apiMessages: Record<string, string> = readJson("platform/messages_ru.json");
const gateSteps: { codes: Record<string, StepTarget> } = readJson("domain/uix/gate_steps.json");
const TARGETS = Object.keys(STEP_LABEL) as StepTarget[];

afterEach(cleanup);

function refusal(over: Partial<ErrorResponse> = {}): ErrorResponse {
  return {
    error: "VALIDITY_FAILED",
    http_status: 409,
    message_ru: "Проверка не пройдена.",
    step: "S9",
    gates: [],
    correlation_id: "c",
    ...over,
  };
}

describe("target steps", () => {
  it("has a label for every target, the same text as the API resources", () => {
    for (const step of TARGETS) {
      expect(ru[STEP_LABEL[step]]).toBe(apiMessages[`step.${step}`]);
    }
    const apiTargets = Object.keys(apiMessages).filter((k) => k.startsWith("step."));
    expect(apiTargets.sort()).toEqual(TARGETS.map((s) => `step.${s}`).sort());
  });

  it("can render every catalogue code's target step", () => {
    for (const [code, step] of Object.entries(gateSteps.codes)) {
      expect(TARGETS, code).toContain(step);
      expect(t(STEP_LABEL[step]).trim(), code).not.toBe("");
    }
  });

  it("routes workflow steps under the case, fixed screens elsewhere, CURRENT nowhere", () => {
    expect(stepPath("S6", "c-1")).toBe("/cases/c-1/anatomy");
    expect(stepPath("S12", "a/b")).toBe("/cases/a%2Fb/records");
    expect(stepPath("S6", null)).toBeNull();
    expect(stepPath("SIGN_IN", null)).toBe("/login");
    expect(stepPath("ADMIN", "c-1")).toBe("/admin");
    expect(stepPath("CURRENT", "c-1")).toBeNull();
    const paths = TARGETS.filter((s) => s.startsWith("S") && s !== "SIGN_IN").map((s) =>
      stepPath(s, "x"),
    );
    expect(new Set(paths).size).toBe(12);
  });

  it("prefers a same-origin server link and ignores any other", () => {
    const gate = { code: "LANDMARKS_INCOMPLETE", message_ru: "m", step: "S6" as const };
    expect(gatePath({ ...gate, link: "/cases/c-1/anatomy#nasion" }, "c-1")).toBe(
      "/cases/c-1/anatomy#nasion",
    );
    for (const link of ["https://evil.test/x", "//evil.test/x", "javascript:alert(1)", null]) {
      expect(gatePath({ ...gate, link }, "c-1")).toBe("/cases/c-1/anatomy");
    }
  });
});

describe("GateList", () => {
  it("shows the API message and each gate with its message and step link", () => {
    render(
      <GateList
        caseId="c-1"
        error={refusal({
          gates: [
            {
              code: "FRAME_NOT_CONFIRMED",
              message_ru: "Подтвердите систему координат.",
              step: "S6",
            },
            { code: "PRESCRIPTION_MISSING", message_ru: "Нет документа.", step: "S2" },
            { code: "VERSION_CONFLICT", message_ru: "Обновите.", step: "CURRENT" },
          ],
        })}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("Проверка не пройдена.")).toBeTruthy();
    const items = within(alert).getAllByRole("listitem");
    expect(items.map((li) => li.dataset.gate)).toEqual([
      "FRAME_NOT_CONFIRMED",
      "PRESCRIPTION_MISSING",
      "VERSION_CONFLICT",
    ]);
    const first = within(items[0]!).getByRole("link");
    expect(first.getAttribute("href")).toBe("/cases/c-1/anatomy");
    expect(first.textContent).toBe(`${t("gates.goTo")}: ${t("step.S6")}`);
    expect(within(items[1]!).getByRole("link").getAttribute("href")).toBe(
      "/cases/c-1/prescription",
    );
    expect(within(items[2]!).queryByRole("link")).toBeNull(); // resolved on this screen
    expect(within(items[2]!).getByText("Обновите.")).toBeTruthy();
  });

  it("links the error itself when there are no gates", () => {
    render(<GateList error={refusal({ error: "SESSION_EXPIRED", step: "SIGN_IN", gates: [] })} />);
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/login");
    expect(screen.queryByRole("listitem")).toBeNull();
  });

  it("shows no link when nothing resolves elsewhere", () => {
    render(<GateList error={refusal({ error: "INTERNAL", step: "CURRENT" })} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("Проверка не пройдена.")).toBeTruthy();
  });
});
