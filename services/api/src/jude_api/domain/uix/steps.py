"""FN-UIX-03 Gate and job status presentation [domain/API] (TSK-UIX-03-B; NFR-05, FR-014, FR-032).

Every error catalogue code has a target step: the place in the workflow where the user resolves
it. The UI renders a gate list as "Russian message + link to that step" without knowing any
domain rule (ADR-008: the server decides gates, the UI only shows them).

Targets (``gate_steps.json``, schema gate-steps/1, one entry per catalogue code):

- ``S1`` … ``S12``: the WF-MVP-01 steps (MVP_SCOPE §1): case, prescription, upload, integrity
  gate, cleanup, anatomy, measurement, design, review, approval, export, records. A code goes to
  the step whose functions resolve it, e.g. FRAME_NOT_CONFIRMED to S6 although measurement (S7)
  and design (S8) raise it.
- ``SIGN_IN``: W01 sign-in (session, credentials, CSRF).
- ``ADMIN``: W07 administration (users, clinic configuration, privacy record); a user without
  the role sees whom to ask.
- ``CURRENT``: resolved where the user already is: a field on the current form, a reload after
  a conflict, or a retry after a transient failure.

The table is navigation, not a clinical rule: it states where a refusal is resolved, never what
to do clinically. Each target has a Russian label ``step.<TARGET>`` in messages_ru.json.
"""

from collections.abc import Mapping
from functools import cache
import json
from pathlib import Path
from typing import Final

HERE = Path(__file__).resolve().parent
WORKFLOW: Final = tuple(f"S{i}" for i in range(1, 13))
TARGETS: Final = (*WORKFLOW, "SIGN_IN", "ADMIN", "CURRENT")


@cache
def gate_steps() -> Mapping[str, str]:
    doc = json.loads((HERE / "gate_steps.json").read_text(encoding="utf-8"))
    if doc.get("schema") != "gate-steps/1":
        raise ValueError("gate_steps.json: schema gate-steps/1 expected")
    steps: Mapping[str, str] = doc["codes"]
    unknown = sorted(c for c, s in steps.items() if s not in TARGETS)
    if unknown:
        raise ValueError(f"gate_steps.json: unknown target step for {unknown}")
    return steps


def target_step(code: str) -> str:
    """The step that resolves ``code``. Raises KeyError for a code without one."""
    return gate_steps()[code]


def step_label_key(step: str) -> str:
    if step not in TARGETS:
        raise KeyError(step)
    return f"step.{step}"
