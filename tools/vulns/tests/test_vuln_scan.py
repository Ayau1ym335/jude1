"""CI-FN-OPS-03 / TC-SEC-09: dependency vulnerability scan (TSK-OPS-03-C; SD-04).

Completion criterion: a seeded vulnerable package fails the release job. Offline tests feed
recorded OSV documents through a fake fetch; the ``security`` test asks the live OSV.dev
database about a seeded jinja2 2.10 (CVE-2019-10906, CVSS 8.6) in the release stage.
"""

from datetime import date
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load() -> ModuleType:
    path = ROOT / "tools/vulns/vuln_scan.py"
    spec = importlib.util.spec_from_file_location("vuln_scan", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["vuln_scan"] = mod
    spec.loader.exec_module(mod)
    return mod


V = _load()
TODAY = "2026-11-25"


# --- CVSS v3 base score (FIRST v3.1 reference values) ---------------------------------------------


@pytest.mark.parametrize(
    ("vector", "score"),
    [
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8),
        ("CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:N/A:N", 8.6),  # CVE-2019-10906 (jinja2)
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H", 10.0),
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H", 7.5),
        ("CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H", 8.1),
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N", 6.1),
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N", 5.4),
        ("CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N", 5.5),
        ("CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:L/I:L/A:N", 6.4),
        ("CVSS:3.1/AV:P/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N", 1.6),
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", 0.0),
    ],
)
def test_cvss3_base_scores(vector: str, score: float) -> None:
    assert V.cvss3_base_score(vector) == score


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N",
        "CVSS:3.1/AV:N/AC:L",
        "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
    ],
)
def test_invalid_vectors(bad: str) -> None:
    with pytest.raises(ValueError):
        V.cvss3_base_score(bad)


# --- fake advisory database -----------------------------------------------------------------------


def advisory(
    vid: str,
    *,
    vector: str | None = None,
    label: str | None = None,
    aliases: list[str] | None = None,
    withdrawn: bool = False,
) -> dict[str, Any]:
    doc: dict[str, Any] = {"id": vid, "aliases": aliases or [], "summary": f"advisory {vid}"}
    if vector:
        doc["severity"] = [{"type": "CVSS_V3", "score": vector}]
    if label:
        doc["database_specific"] = {"severity": label}
    if withdrawn:
        doc["withdrawn"] = "2026-01-01T00:00:00Z"
    return doc


HIGH = advisory("GHSA-high", vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H")  # 7.5
MEDIUM = advisory("GHSA-medium", vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N")  # 5.4
LABEL_HIGH = advisory("GHSA-label", label="HIGH")
UNSCORED = advisory("PYSEC-none")
ALIAS_OF_MEDIUM = advisory("PYSEC-dup", aliases=["GHSA-medium", "CVE-2026-1"])
WITHDRAWN = advisory(
    "GHSA-gone", vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", withdrawn=True
)


class FakeOSV:
    def __init__(self, by_package: dict[str, list[dict[str, Any]]]) -> None:
        self.by_package, self.docs = by_package, {}
        for docs in by_package.values():
            self.docs.update({d["id"]: d for d in docs})
        self.calls = 0

    def __call__(self, url: str, body: dict[str, Any] | None) -> dict[str, Any]:
        self.calls += 1
        if url.endswith("/querybatch"):
            assert body is not None
            return {
                "results": [
                    {
                        "vulns": [
                            {"id": d["id"]} for d in self.by_package.get(q["package"]["name"], [])
                        ]
                    }
                    for q in body["queries"]
                ]
            }
        return self.docs[url.rsplit("/", 1)[1]]


def inventory(tmp_path: Path, *names: str) -> Path:
    path = tmp_path / "inventory.json"
    path.write_text(
        json.dumps(
            [
                {
                    "ecosystem": "pypi",
                    "component": "jude-api",
                    "name": n,
                    "version": "1.0",
                    "licence": "MIT",
                    "supplier": "",
                }
                for n in names
            ]
        ),
        encoding="utf-8",
    )
    return path


def acceptances(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    path = tmp_path / "accepted.json"
    path.write_text(json.dumps({"schema": "vuln-acceptance/1", "accepted": entries}), "utf-8")
    return path


def run(
    tmp_path: Path,
    osv: Any,
    *names: str,
    accepted: list[dict[str, Any]] | None = None,
    today: str = TODAY,
) -> tuple[int, dict[str, Any]]:
    report = tmp_path / "vulns.json"
    argv = [
        "--inventory",
        str(inventory(tmp_path, *names)),
        "--report",
        str(report),
        "--accepted",
        str(acceptances(tmp_path, accepted or [])),
        "--today",
        today,
    ]
    code = V.main(argv, fetch=osv)
    return code, (json.loads(report.read_text(encoding="utf-8")) if report.exists() else {})


def accept(
    vid: str,
    package: str = "lib",
    expires: str = "2027-01-31",
    approver: str = "A. Engineering Lead",
) -> dict[str, Any]:
    return {
        "id": vid,
        "ecosystem": "pypi",
        "package": package,
        "approver": approver,
        "reason": "not reachable from our code path",
        "recorded": "2026-11-20",
        "expires": expires,
    }


# --- completion criterion (offline) ---------------------------------------------------------------


def test_completion_criterion_seeded_vulnerable_package_fails(tmp_path: Path) -> None:
    code, doc = run(tmp_path, FakeOSV({"lib": [HIGH]}), "fastapi", "lib")
    assert code == 1 and doc["blocking"] == 1
    (finding,) = doc["findings"]
    assert (finding["package"], finding["id"], finding["score"], finding["blocking"]) == (
        "lib",
        "GHSA-high",
        7.5,
        True,
    )


def test_clean_inventory_passes(tmp_path: Path) -> None:
    code, doc = run(tmp_path, FakeOSV({}), "fastapi", "numpy")
    assert (code, doc["blocking"], doc["scanned_packages"], doc["findings"]) == (0, 0, 2, [])


# --- scoring --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("docs", "code", "basis"),
    [
        ([MEDIUM], 0, "cvss3"),  # below 7.0: reported, not blocking
        ([LABEL_HIGH], 1, "label"),  # no vector: GitHub label HIGH -> 7.0
        ([UNSCORED], 1, "unscored"),  # nobody scored it: fail closed
        ([MEDIUM, ALIAS_OF_MEDIUM], 0, "alias:GHSA-medium"),  # same vulnerability, scored twin
        ([WITHDRAWN], 0, None),  # withdrawn advisories are ignored
    ],
)
def test_scores(tmp_path: Path, docs: list[dict[str, Any]], code: int, basis: str | None) -> None:
    got, doc = run(tmp_path, FakeOSV({"lib": docs}), "lib")
    assert got == code
    if basis is None:
        assert doc["findings"] == []
    else:
        assert doc["findings"][-1]["basis"] == basis


def test_each_advisory_is_fetched_once(tmp_path: Path) -> None:
    osv = FakeOSV({"lib": [HIGH], "other": [HIGH]})
    run(tmp_path, osv, "lib", "other")
    assert osv.calls == 2  # one batch query + one detail fetch for the shared advisory


# --- risk acceptance ------------------------------------------------------------------------------


def test_named_acceptance_lifts_the_block_until_it_expires(tmp_path: Path) -> None:
    osv = FakeOSV({"lib": [HIGH]})
    code, doc = run(tmp_path, osv, "lib", accepted=[accept("GHSA-high")])
    assert code == 0 and doc["findings"][0]["accepted_by"] == "A. Engineering Lead"
    code, doc = run(tmp_path, osv, "lib", accepted=[accept("GHSA-high", expires="2026-11-24")])
    assert code == 1 and "expired 2026-11-24" in doc["findings"][0]["notes"][0]


def test_acceptance_by_alias_and_only_for_its_package(tmp_path: Path) -> None:
    osv = FakeOSV({"lib": [advisory("GHSA-x", label="CRITICAL", aliases=["CVE-2026-9"])]})
    assert run(tmp_path, osv, "lib", accepted=[accept("CVE-2026-9")])[0] == 0
    assert run(tmp_path, osv, "lib", accepted=[accept("CVE-2026-9", package="other")])[0] == 1


@pytest.mark.parametrize("missing", ["approver", "reason", "expires"])
def test_acceptance_needs_a_named_approver_reason_and_expiry(tmp_path: Path, missing: str) -> None:
    entry = accept("GHSA-high")
    entry[missing] = " "
    assert run(tmp_path, FakeOSV({"lib": [HIGH]}), "lib", accepted=[entry])[0] == 2


# --- the gate fails closed ------------------------------------------------------------------------


def test_unreachable_database_fails_the_gate(tmp_path: Path) -> None:
    def down(url: str, body: dict[str, Any] | None) -> dict[str, Any]:
        raise urllib.error.URLError("no route to api.osv.dev")

    assert run(tmp_path, down, "lib")[0] == 2


def test_incomplete_answer_fails_the_gate(tmp_path: Path) -> None:
    assert run(tmp_path, lambda url, body: {"results": []}, "lib", "other")[0] == 2


def test_report_shape(tmp_path: Path) -> None:
    _, doc = run(tmp_path, FakeOSV({"lib": [HIGH, MEDIUM]}), "lib")
    assert (doc["schema"], doc["database"], doc["threshold_cvss"], doc["date"]) == (
        "vuln-report/1",
        "OSV.dev",
        7.0,
        TODAY,
    )
    assert [f["id"] for f in doc["findings"]] == ["GHSA-high", "GHSA-medium"]
    assert date.fromisoformat(doc["date"]) == date(2026, 11, 25)


# --- live database (release stage) ----------------------------------------------------------------


@pytest.mark.security
def test_live_seeded_vulnerable_package_fails_the_release_gate(tmp_path: Path) -> None:
    """Completion criterion against OSV.dev: jinja2 2.10 carries CVE-2019-10906 (CVSS 8.6)."""
    report = tmp_path / "vulns.json"
    argv = ["--inventory", str(inventory(tmp_path, "jinja2")), "--report", str(report)]
    path = tmp_path / "inventory.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows[0]["version"] = "2.10"
    path.write_text(json.dumps(rows), encoding="utf-8")
    assert V.main(argv) == 1
    doc = json.loads(report.read_text(encoding="utf-8"))
    ids = {a for f in doc["findings"] if f["blocking"] for a in (f["id"], *f["aliases"])}
    assert "CVE-2019-10906" in ids
