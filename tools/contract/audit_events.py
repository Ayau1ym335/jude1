"""Audit event catalogue check (TSK-AUD-01-A, FN-AUD-01 step 1): run by the CI contract stage.

    python tools/contract/audit_events.py

Fails when an event type named by FUNCTION_TECHNICAL_SPECIFICATIONS_v1.0 is missing from
services/api/src/jude_api/platform/audit_events.json, when a catalogued type is no longer named
anywhere (except reserved AI-10 types), or when the reserved ai.* types are not reserved.
Tokens that look like event types but are fields, paths or op types are listed in NON_EVENTS.
"""

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = ROOT / "services/api/src/jude_api/platform/audit_events.json"
FS = ROOT / "docs/design/FUNCTION_TECHNICAL_SPECIFICATIONS_v1.0.md"
PREFIXES = (
    "auth|account|authz|case|scan|design|approval|export|config|user|job|audit|landmark|frame|"
    "measurement|prescription|review|report|session|ai|blob|definition|zone"
)
TOKEN = re.compile(rf"\b(?:{PREFIXES})\.[a-z_]+(?:\.[a-z_]+)?\b")
RESERVED = {
    "ai.dataset.exported", "ai.model.registered", "ai.model.enabled", "ai.model.disabled",
    "ai.suggestion.resolved",
}  # fmt: skip
NON_EVENTS = {
    "account.locked_until": "column",
    "approval.geometry_sha": "column",
    "approval.reapproval_required": "column",
    "audit.csv": "endpoint path",
    "job.status": "column",
    "scan.status": "column",
    "zone.normal_falloff": "op type",
}


def problems() -> list[str]:
    types = json.loads(CATALOGUE.read_text(encoding="utf-8"))["types"]
    named = set(TOKEN.findall(FS.read_text(encoding="utf-8"))) - set(NON_EVENTS)
    out = [f"{t}: named by the FS but not catalogued" for t in sorted(named - set(types))]
    out += [
        f"{t}: catalogued but not named by the FS"
        for t, e in sorted(types.items())
        if t not in named and not e["reserved"]
    ]
    out += [
        f"{t}: must be reserved (AI-10)"
        for t in sorted(RESERVED)
        if not types.get(t, {}).get("reserved")
    ]
    out += [
        f"{t}: only AI-10 types are reserved"
        for t, e in types.items()
        if e["reserved"] and t not in RESERVED
    ]
    return out


def main() -> int:
    found = problems()
    for p in found:
        print(f"AUDIT-EVENTS {p}")
    if found:
        return 1
    print("audit event catalogue: every FS event type covered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
