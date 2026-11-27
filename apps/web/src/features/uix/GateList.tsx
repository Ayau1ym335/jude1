// FN-UIX-03 gate list (TSK-UIX-03-U). Generic over any DS-24 refusal (ADR-008): the API's
// Russian message, then each gate with its own message and a link to the step that resolves
// it. All text comes from the server or the message resources (NFR-05, VER-09).
import type { ErrorResponse } from "@jude/contracts";

import { t } from "../../i18n";
import { STEP_LABEL, gatePath, stepPath } from "./steps";

type Props = {
  error: ErrorResponse;
  /** The case the screen belongs to; workflow-step links need it. */
  caseId?: string | null;
};

export function GateList({ error, caseId = null }: Props) {
  const gates = error.gates;
  const top = gates.length === 0 ? stepPath(error.step, caseId) : null;
  return (
    <div role="alert" data-error={error.error}>
      <p>{error.message_ru}</p>
      {top !== null && <StepLink href={top} step={error.step} />}
      {gates.length > 0 && (
        <ul>
          {gates.map((gate, i) => {
            const href = gatePath(gate, caseId);
            return (
              <li key={`${gate.code}-${i}`} data-gate={gate.code}>
                <span>{gate.message_ru}</span>
                {href !== null && <StepLink href={href} step={gate.step} />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function StepLink({ href, step }: { href: string; step: ErrorResponse["step"] }) {
  return (
    <a href={href} data-step={step}>
      {`${t("gates.goTo")}: ${t(STEP_LABEL[step])}`}
    </a>
  );
}
