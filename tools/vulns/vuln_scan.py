"""Dependency vulnerability scan (FN-OPS-03, TSK-OPS-03-C; SEC-09, SD-04).

Blocks a release while a shipped package has an unresolved vulnerability with CVSS >= 7.0.
"Unresolved" means there is no recorded risk acceptance by a named approver.

**Inventory.** The shipped packages, exactly as the licence check collects them (FN-OPS-02):
the image dependency closures of jude-api and jude-worker, and the production closure of
@jude/web.

**Advisories.** OSV.dev (``/v1/querybatch``, then ``/v1/vulns/{id}``). It aggregates the
GitHub Advisory Database, PyPA and others. Withdrawn advisories are ignored.

**Score of an advisory**, the first of:
1. the highest CVSS v3.x base score among its ``CVSS_V3`` vectors, computed with the FIRST
   CVSS 3.1 equations (``cvss3_base_score``);
2. the GitHub severity label, mapped onto the CVSS bands it stands for (CRITICAL 9.0,
   HIGH 7.0, MODERATE 4.0, LOW 0.1);
3. otherwise unscored, which is treated as blocking. An advisory nobody has scored is not
   assumed harmless (fail closed).

**Risk acceptance** (``accepted.json``): an entry names the advisory (its id or an alias),
the package, a named approver, a reason, the recording date and an expiry date. An expired
acceptance no longer counts.

**Result.** The JSON report lists every finding with its score, basis and acceptance. Exit
status: 0 when nothing blocks; 1 when a finding blocks the release; 2 on a configuration
error or when the advisory database cannot be reached. The gate never passes without
having asked.

Usage:
  python tools/vulns/vuln_scan.py [--report reports/vulns.json] [--inventory inv.json]
                                  [--accepted tools/vulns/accepted.json] [--today YYYY-MM-DD]
"""

import argparse
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
import importlib.util
import json
import math
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Final
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ACCEPTED = HERE / "accepted.json"
OSV: Final = "https://api.osv.dev/v1"
THRESHOLD: Final = 7.0  # SD-04
LABEL_SCORES: Final = {"CRITICAL": 9.0, "HIGH": 7.0, "MODERATE": 4.0, "MEDIUM": 4.0, "LOW": 0.1}
ECOSYSTEMS: Final = {"pypi": "PyPI", "npm": "npm"}
TIMEOUT_S: Final = 30.0

Fetch = Callable[[str, dict[str, Any] | None], dict[str, Any]]


# --- CVSS v3.x base score (FIRST CVSS v3.1 specification, section 7) ------------------------------

_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}
_AC = {"L": 0.77, "H": 0.44}
_PR_U = {"N": 0.85, "L": 0.62, "H": 0.27}
_PR_C = {"N": 0.85, "L": 0.68, "H": 0.5}
_UI = {"N": 0.85, "R": 0.62}
_CIA = {"H": 0.56, "L": 0.22, "N": 0.0}
_REQUIRED = ("AV", "AC", "PR", "UI", "S", "C", "I", "A")


def _roundup(x: float) -> float:
    """CVSS v3.1 Roundup: the smallest one-decimal number >= x, free of float artefacts."""
    i = round(x * 100000)
    return i / 100000.0 if i % 10000 == 0 else (math.floor(i / 10000) + 1) / 10.0


def cvss3_base_score(vector: str) -> float:
    parts = vector.strip().split("/")
    if not parts or not parts[0].startswith("CVSS:3."):
        raise ValueError(f"not a CVSS v3 vector: {vector!r}")
    m = dict(p.split(":", 1) for p in parts[1:] if ":" in p)
    if any(k not in m for k in _REQUIRED):
        raise ValueError(f"incomplete CVSS v3 vector: {vector!r}")
    changed = m["S"] == "C"
    iss = 1 - (1 - _CIA[m["C"]]) * (1 - _CIA[m["I"]]) * (1 - _CIA[m["A"]])
    impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if changed else 6.42 * iss
    pr = (_PR_C if changed else _PR_U)[m["PR"]]
    exploitability = 8.22 * _AV[m["AV"]] * _AC[m["AC"]] * pr * _UI[m["UI"]]
    if impact <= 0:
        return 0.0
    total = 1.08 * (impact + exploitability) if changed else impact + exploitability
    return _roundup(min(total, 10.0))


# --- findings -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    ecosystem: str
    package: str
    version: str
    component: str
    id: str
    aliases: tuple[str, ...]
    summary: str
    score: float | None
    basis: str  # cvss3 | label | unscored
    accepted_by: str | None = None
    notes: tuple[str, ...] = field(default=())

    @property
    def blocking(self) -> bool:
        severe = self.score is None or self.score >= THRESHOLD
        return severe and self.accepted_by is None


def advisory_score(doc: dict[str, Any]) -> tuple[float | None, str]:
    scores = []
    for sev in doc.get("severity") or []:
        if sev.get("type") == "CVSS_V3":
            try:
                scores.append(cvss3_base_score(sev["score"]))
            except (KeyError, ValueError):
                continue
    if scores:
        return max(scores), "cvss3"
    label = str((doc.get("database_specific") or {}).get("severity", "")).upper()
    if label in LABEL_SCORES:
        return LABEL_SCORES[label], "label"
    return None, "unscored"


def load_acceptances(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "vuln-acceptance/1":
        raise ValueError(f"{path}: schema must be vuln-acceptance/1")
    for a in data["accepted"]:
        for key in ("id", "ecosystem", "package", "approver", "reason", "recorded", "expires"):
            if not str(a.get(key, "")).strip():
                raise ValueError(f"{path}: acceptance {a.get('id')} needs {key!r}")
        date.fromisoformat(a["recorded"])
        date.fromisoformat(a["expires"])
    accepted: list[dict[str, Any]] = data["accepted"]
    return accepted


def _acceptance(
    f: Finding, acceptances: Iterable[dict[str, Any]], today: date
) -> tuple[str | None, tuple[str, ...]]:
    names = {f.id, *f.aliases}
    for a in acceptances:
        if a["id"] in names and (a["ecosystem"], a["package"]) == (f.ecosystem, f.package):
            if date.fromisoformat(a["expires"]) < today:
                return None, (f"acceptance by {a['approver']} expired {a['expires']}",)
            return a["approver"], (f"accepted by {a['approver']} until {a['expires']}",)
    return None, ()


def scan(
    packages: Sequence[Any],
    fetch: Fetch,
    acceptances: Sequence[dict[str, Any]],
    today: date,
) -> list[Finding]:
    queries = [
        {"package": {"name": p.name, "ecosystem": ECOSYSTEMS[p.ecosystem]}, "version": p.version}
        for p in packages
    ]
    results = fetch(f"{OSV}/querybatch", {"queries": queries}).get("results", [])
    if len(results) != len(packages):
        raise RuntimeError("advisory database answered a different number of queries")
    details: dict[str, dict[str, Any]] = {}
    findings = []
    for p, result in zip(packages, results, strict=True):
        for v in result.get("vulns") or []:
            vid = v["id"]
            if vid not in details:
                details[vid] = fetch(f"{OSV}/vulns/{vid}", None)
            doc = details[vid]
            if doc.get("withdrawn"):
                continue
            score, basis = advisory_score(doc)
            f = Finding(
                p.ecosystem,
                p.name,
                p.version,
                p.component,
                vid,
                tuple(sorted(doc.get("aliases") or [])),
                str(doc.get("summary") or "")[:200],
                score,
                basis,
            )
            findings.append(f)
    findings = _score_from_aliases(findings)
    accepted = []
    for f in findings:
        approver, notes = _acceptance(f, acceptances, today)
        accepted.append(Finding(**{**f.__dict__, "accepted_by": approver, "notes": notes}))
    return sorted(accepted, key=lambda f: (f.ecosystem, f.package, f.version, f.id))


def _score_from_aliases(findings: list[Finding]) -> list[Finding]:
    """An unscored advisory takes the score of a scored record of the same vulnerability.

    Databases republish one vulnerability under several ids (PYSEC-…, GHSA-…, CVE-…). Two
    findings for the same package version are the same vulnerability when their id/alias
    sets overlap. An unscored record with no scored relative stays unscored (blocking).
    """
    out = []
    for f in findings:
        if f.score is not None:
            out.append(f)
            continue
        names = {f.id, *f.aliases}
        relatives = [
            g
            for g in findings
            if g.score is not None
            and (g.ecosystem, g.package, g.version) == (f.ecosystem, f.package, f.version)
            and names & {g.id, *g.aliases}
        ]
        if relatives:
            best = max(relatives, key=lambda g: (g.score or 0.0, g.id))
            out.append(Finding(**{**f.__dict__, "score": best.score, "basis": f"alias:{best.id}"}))
        else:
            out.append(f)
    return out


def osv_fetch(url: str, body: dict[str, Any] | None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(  # noqa: S310 - fixed https URL of the advisory database
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310
        doc: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return doc


def _licence_check() -> ModuleType:
    path = ROOT / "tools" / "licences" / "licence_check.py"
    spec = importlib.util.spec_from_file_location("licence_check", path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - repository file
    mod = importlib.util.module_from_spec(spec)
    sys.modules["licence_check"] = mod
    spec.loader.exec_module(mod)
    return mod


def report(findings: Sequence[Finding], scanned: int, today: date) -> dict[str, Any]:
    return {
        "schema": "vuln-report/1",
        "database": "OSV.dev",
        "date": today.isoformat(),
        "threshold_cvss": THRESHOLD,
        "scanned_packages": scanned,
        "blocking": sum(f.blocking for f in findings),
        "findings": [{**f.__dict__, "blocking": f.blocking} for f in findings],
    }


def main(argv: list[str] | None = None, fetch: Fetch = osv_fetch) -> int:
    parser = argparse.ArgumentParser(prog="vuln_scan")
    parser.add_argument("--inventory", type=Path, help="scan this inventory (licence_check format)")
    parser.add_argument("--accepted", type=Path, default=ACCEPTED)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--today", type=date.fromisoformat, default=datetime.now(UTC).date())
    args = parser.parse_args(argv)
    out = sys.stdout
    if hasattr(out, "reconfigure"):
        out.reconfigure(encoding="utf-8")
    lc = _licence_check()
    try:
        acceptances = load_acceptances(args.accepted)
        if args.inventory:
            raw = json.loads(args.inventory.read_text(encoding="utf-8"))
            packages = sorted((lc.Package(**p) for p in raw), key=lc._key)
        else:
            packages = lc.collect()
        findings = scan(packages, fetch, acceptances, args.today)
    except (OSError, ValueError, KeyError, RuntimeError, urllib.error.URLError) as exc:
        sys.stderr.write(f"vulnerability scan: {exc}\n")
        return 2
    for f in findings:
        score = "unscored" if f.score is None else f"{f.score:.1f}"
        flag = "BLOCKING" if f.blocking else ("accepted" if f.accepted_by else "below 7.0")
        out.write(
            f"VUL001 {f.ecosystem}:{f.package}=={f.version} {f.id} CVSS {score} "
            f"({f.basis}) {flag} {' '.join(f.notes)}\n"
        )
    doc = report(findings, len(packages), args.today)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    out.write(
        f"vulnerability scan: {len(packages)} shipped packages, {len(findings)} "
        f"advisories, {doc['blocking']} blocking (CVSS >= {THRESHOLD})\n"
    )
    return 1 if doc["blocking"] else 0


if __name__ == "__main__":
    sys.exit(main())
