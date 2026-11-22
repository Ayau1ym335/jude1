"""Error catalogue check (TSK-API-02-A, FN-API-02, IDR-05): run by the CI ``contract`` stage.

    python tools/contract/error_catalogue.py [--base-ref REF]

Fails (exit 1) when:

1. a code used by any function of FUNCTION_TECHNICAL_SPECIFICATIONS_v1.0, or named by RTM
   v0.3/v0.4, is missing from the catalogue. A code is any UPPER_SNAKE token in those documents
   except the tokens in ``NON_CODES`` (document names, symbols, status values);
2. the catalogue is inconsistent: a ``refusal`` without a 4xx/5xx ``http_status`` or another
   kind with one, a message key without a Russian message, or a message without a code;
3. Python code raises a code that is not catalogued (``ApiError("X")``, ``error_response("X")``);
4. with ``--base-ref``: a code was removed, or the ``http_status`` or ``kind`` of an existing
   code changed. Codes are stable (DS-24); a rename is a new code, never an edit.
"""

import argparse
from collections.abc import Iterable
import csv
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = Path("services/api/src/jude_api/platform/error_catalogue.json")
MESSAGES = Path("services/api/src/jude_api/platform/messages_ru.json")
FS = Path("docs/design/FUNCTION_TECHNICAL_SPECIFICATIONS_v1.0.md")
RTMS = (
    Path("docs/design/04a_REQUIREMENTS_TRACEABILITY_MATRIX_v0.3.csv"),
    Path("docs/design/04a_REQUIREMENTS_TRACEABILITY_MATRIX_v0.4.csv"),
)
SOURCE_DIRS = (Path("services"), Path("packages"))
KINDS = {"refusal", "kernel", "job", "measurement", "warning", "startup"}
TOKEN = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
RAISED = re.compile(r"\b(?:ApiError|error_response|error_body)\(\s*[\"']([A-Z][A-Z0-9_]*)[\"']")

# UPPER_SNAKE tokens in the FS / RTM that are not error codes. A new token must be added here
# (with its reason) or to the catalogue: the check never guesses.
NON_CODES: dict[str, str] = {
    # document names cited in the text
    "TECHNICAL_DESIGN": "document", "ALGORITHM_CATALOG": "document",
    "CAD_GEOMETRY_ENGINE_DESIGN": "document", "LIBRARY_COMPARISON": "document",
    "VERIFICATION_CRITERIA": "document", "VERIFICATION_CRITERIA_PROPOSALS": "document",
    "APPROVAL_GOVERNANCE": "document", "ARTIFACT_PLAN": "document",
    "DOMAIN_GLOSSARY": "document", "PRODUCT_BRIEF": "document",
    "DECISION_RECORD_2026": "document",
    # mathematical symbols
    "F_S": "symbol (scan face set)", "V_A": "symbol", "V_P": "symbol", "V_S": "symbol",
    # status values that carry a reason code, not codes themselves
    "NOT_SET": "config value state (DEC-029); refusals use CONFIG_NOT_SET / PARAM_NOT_SET",
    "NOT_COMPUTED": "measurement status; the reason is a 'measurement' code",
    "NOT_APPLICABLE": "measurement/anchor result status",
}  # fmt: skip


def _read(path: Path) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def tokens(text: str) -> set[str]:
    return set(TOKEN.findall(text))


def spec_codes() -> dict[str, set[str]]:
    """Code -> where it is used (FN ids for the FS, requirement ids for the RTM)."""
    used: dict[str, set[str]] = {}
    fn = "FS"
    for line in _read(FS).splitlines():
        m = re.match(r"^#### (FN-[A-Z0-9.-]+) ", line)
        if m:
            fn = m.group(1)
        for t in tokens(line):
            used.setdefault(t, set()).add(fn)
    for rtm in RTMS:
        for row in csv.DictReader(_read(rtm).splitlines()):
            for value in row.values():
                for t in tokens(value or ""):
                    used.setdefault(t, set()).add(f"{row['id']} ({rtm.stem[-4:]})")
    return {t: s for t, s in used.items() if t not in NON_CODES}


def raised_codes(dirs: Iterable[Path] = SOURCE_DIRS) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for d in dirs:
        for py in sorted((ROOT / d).rglob("*.py")):
            if "tests" in py.parts or ".venv" in py.parts or "node_modules" in py.parts:
                continue
            for code in RAISED.findall(py.read_text(encoding="utf-8")):
                found.setdefault(code, set()).add(py.relative_to(ROOT).as_posix())
    return found


def consistency(catalogue: dict[str, Any], messages: dict[str, str]) -> list[str]:
    problems: list[str] = []
    if catalogue.get("schema") != "error/1":
        problems.append("catalogue schema must be 'error/1'")
    codes: dict[str, dict[str, Any]] = catalogue["codes"]
    for code, e in codes.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*", code):
            problems.append(f"{code}: not an UPPER_SNAKE code")
        if e.get("kind") not in KINDS:
            problems.append(f"{code}: unknown kind {e.get('kind')!r}")
        status = e.get("http_status")
        if e.get("kind") == "refusal":
            if not (isinstance(status, int) and 400 <= status <= 599):
                problems.append(f"{code}: a refusal needs a 4xx/5xx http_status")
        elif status is not None:
            problems.append(f"{code}: only refusals carry an http_status")
        if e.get("message_key") != f"error.{code.lower()}":
            problems.append(f"{code}: message_key must be error.{code.lower()}")
        elif e["message_key"] not in messages or not messages[e["message_key"]].strip():
            problems.append(f"{code}: no Russian message for {e['message_key']}")
        if not e.get("sources"):
            problems.append(f"{code}: no source (FS function, RTM requirement or task)")
    keys = {e.get("message_key") for e in codes.values()}
    for key in sorted(set(messages) - keys):
        problems.append(f"message {key} has no code")
    return problems


def coverage(catalogue: dict[str, Any]) -> list[str]:
    codes = catalogue["codes"]
    out = [
        f"{code}: used by {', '.join(sorted(where)[:4])} but not in the catalogue"
        for code, where in sorted(spec_codes().items())
        if code not in codes
    ]
    out += [
        f"{code}: raised in {', '.join(sorted(where))} but not in the catalogue"
        for code, where in sorted(raised_codes().items())
        if code not in codes
    ]
    return out


def stability(old: dict[str, Any], new: dict[str, Any], label: str) -> list[str]:
    out = []
    for code, e in sorted(old["codes"].items()):
        if code not in new["codes"]:
            out.append(f"{code}: removed (present at {label}); codes are never removed or renamed")
            continue
        n = new["codes"][code]
        for field in ("http_status", "kind"):
            if e.get(field) != n.get(field):
                out.append(f"{code}: {field} changed {e.get(field)!r} -> {n.get(field)!r}")
    return out


def _at_ref(ref: str, path: Path) -> dict[str, Any] | None:
    proc = subprocess.run(  # noqa: S603 — fixed argv
        ["git", "show", f"{ref}:{path.as_posix()}"],  # noqa: S607
        capture_output=True, text=True, encoding="utf-8", check=False, cwd=ROOT,
    )  # fmt: skip
    if proc.returncode != 0:
        if "does not exist" in proc.stderr or "exists on disk" in proc.stderr:
            return None
        raise ValueError(f"cannot read {path} at {ref}: {proc.stderr.strip()}")
    old: dict[str, Any] = json.loads(proc.stdout)
    return old if old.get("schema") == "error/1" else None  # drafts before error/1 are not bound


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-ref", help="also check stability against this git ref")
    args = parser.parse_args(argv)
    catalogue = json.loads(_read(CATALOGUE))
    messages = json.loads(_read(MESSAGES))
    problems = consistency(catalogue, messages) + coverage(catalogue)
    if args.base_ref:
        try:
            old = _at_ref(args.base_ref, CATALOGUE)
        except ValueError as exc:
            print(f"error_catalogue: {exc}", file=sys.stderr)
            return 2
        if old is not None:
            problems += stability(old, catalogue, args.base_ref)
    for p in problems:
        print(f"CATALOGUE {p}")
    if problems:
        print(f"{len(problems)} error-catalogue problem(s)", file=sys.stderr)
        return 1
    print(f"error catalogue: {len(catalogue['codes'])} codes; every FS/RTM code covered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
