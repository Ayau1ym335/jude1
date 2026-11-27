// FN-UIX-03 target steps on the client (TSK-UIX-03-U; NFR-05, FR-014, FR-032, ADR-008).
//
// The server decides every gate and names the step that resolves it (`step`, gate-steps/1,
// TSK-UIX-03-B). The client only turns that step into a label and a link; it never decides
// a gate or builds wording from a code.
//
// Routes: case-scoped workflow steps live under /cases/{caseId}/<slug>. SIGN_IN and ADMIN have
// fixed routes. CURRENT means "resolve it here", so there is no link.
import type { components } from "@jude/contracts";

import type { MessageKey } from "../../i18n";

export type StepTarget = components["schemas"]["Gate"]["step"];
export type Gate = components["schemas"]["Gate"];

export const STEP_LABEL: Record<StepTarget, MessageKey> = {
  S1: "step.S1",
  S2: "step.S2",
  S3: "step.S3",
  S4: "step.S4",
  S5: "step.S5",
  S6: "step.S6",
  S7: "step.S7",
  S8: "step.S8",
  S9: "step.S9",
  S10: "step.S10",
  S11: "step.S11",
  S12: "step.S12",
  SIGN_IN: "step.SIGN_IN",
  ADMIN: "step.ADMIN",
  CURRENT: "step.CURRENT",
};

const CASE_STEP_SLUG: Partial<Record<StepTarget, string>> = {
  S1: "case",
  S2: "prescription",
  S3: "upload",
  S4: "integrity",
  S5: "cleanup",
  S6: "anatomy",
  S7: "measurement",
  S8: "design",
  S9: "review",
  S10: "approval",
  S11: "export",
  S12: "records",
};

/** Where the user resolves `step`; null when there is nowhere to go (CURRENT, or no case). */
export function stepPath(step: StepTarget, caseId: string | null): string | null {
  if (step === "SIGN_IN") return "/login";
  if (step === "ADMIN") return "/admin";
  const slug = CASE_STEP_SLUG[step];
  if (slug === undefined || caseId === null) return null;
  return `/cases/${encodeURIComponent(caseId)}/${slug}`;
}

/** A server-supplied gate link wins when it is a same-origin path; anything else is ignored. */
export function gatePath(gate: Gate, caseId: string | null): string | null {
  const link = gate.link;
  if (typeof link === "string" && link.startsWith("/") && !link.startsWith("//")) return link;
  return stepPath(gate.step, caseId);
}
