"""CI-FN-OPS-02 / TC-SEC-09: licence allow-list and SOUP list (TSK-OPS-02-C).

Completion criterion: adding a GPL package to a shipped lockfile fails CI. Here it is shown on
synthetic inventories; the lint self-test seeds a GPL package into the inventory collected from
the real lockfiles.
"""

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load() -> ModuleType:
    path = ROOT / "tools/licences/licence_check.py"
    spec = importlib.util.spec_from_file_location("licence_check", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["licence_check"] = mod
    spec.loader.exec_module(mod)
    return mod


L = _load()
POLICY: dict[str, Any] = L.load_policy()
ALLOWED, EXC = POLICY["allowed"], POLICY["allowed_with_exceptions"]


def pkg(name: str, licence: str, eco: str = "pypi", version: str = "1.0") -> Any:
    return L.Package(eco, "jude-api" if eco == "pypi" else "@jude/web", name, version, licence, "")


def inventory(tmp_path: Path, packages: list[Any]) -> Path:
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps([vars(p) for p in packages]), encoding="utf-8")
    return path


CLEAN = [
    pkg("fastapi", "MIT"),
    pkg("numpy", "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0"),
    pkg("psycopg", "LGPL-3.0-only"),
    pkg("llvmlite", "BSD-2-Clause AND Apache-2.0 WITH LLVM-exception"),
    pkg("react", "MIT", "npm"),
    pkg("tslib", "0BSD", "npm"),
]


# --- completion criterion ---------------------------------------------------------------------


def test_completion_criterion_clean_inventory_passes(tmp_path: Path) -> None:
    assert L.main(["--inventory", str(inventory(tmp_path, CLEAN))]) == 0


@pytest.mark.parametrize(
    ("bad", "eco"),
    [
        ("GPL-3.0-only", "pypi"),
        ("GPL-2.0-or-later", "pypi"),
        ("AGPL-3.0-only", "npm"),
        ("GPL-3.0-or-later", "npm"),
    ],
)
def test_completion_criterion_a_gpl_package_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], bad: str, eco: str
) -> None:
    seeded = [*CLEAN, pkg("copyleft-lib", bad, eco, "2.0")]
    assert L.main(["--inventory", str(inventory(tmp_path, seeded))]) == 1
    out = capsys.readouterr().out
    assert f"LIC001 {eco}:copyleft-lib==2.0" in out and bad in out and "1 violation" in out


# --- SPDX evaluation ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expr", "ok"),
    [
        ("MIT", True),
        ("mit", True),  # SPDX ids match case-insensitively
        ("GPL-3.0-only", False),
        ("MIT OR GPL-3.0-only", True),  # a choice: the allowed branch can be taken
        ("MIT AND GPL-3.0-only", False),  # both apply
        ("(MIT OR GPL-2.0-only) AND Apache-2.0", True),
        ("(GPL-2.0-only OR AGPL-3.0-only) AND MIT", False),
        ("Apache-2.0 WITH LLVM-exception", True),
        ("GPL-2.0-only WITH Classpath-exception-2.0", False),  # an exception cannot cure GPL
        ("MIT WITH Some-unknown-exception", False),
        ("MIT-0", False),  # not on the list: only the cffi exception allows it
        ("CC-BY-4.0", False),
        ("SSPL-1.0", False),
        ("Commercial", False),
    ],
)
def test_spdx_expressions(expr: str, ok: bool) -> None:
    assert L.spdx_allowed(expr, ALLOWED, EXC) is ok


@pytest.mark.parametrize(
    "bad", ["", "MIT AND", "(MIT", "MIT)", "AND MIT", "MIT OR OR BSD-3-Clause", "MIT; BSD"]
)
def test_malformed_expressions_are_errors(bad: str) -> None:
    with pytest.raises(ValueError):
        L.spdx_allowed(bad, ALLOWED, EXC)


# --- judgement ------------------------------------------------------------------------------------


def test_exceptions_are_pinned_to_package_and_licence() -> None:
    assert L.judge(pkg("cffi", "MIT-0"), POLICY).ok
    assert L.judge(pkg("caniuse-lite", "CC-BY-4.0", "npm"), POLICY).basis == "exception"
    assert not L.judge(pkg("cffi", "GPL-3.0-only"), POLICY).ok  # the licence changed
    assert not L.judge(pkg("other-lib", "MIT-0"), POLICY).ok  # another package
    assert not L.judge(pkg("caniuse-lite", "CC-BY-4.0", "pypi"), POLICY).ok  # another ecosystem


def test_overrides_need_the_exact_declared_text() -> None:
    v = L.judge(pkg("numba", "BSD"), POLICY)
    assert (v.ok, v.licence, v.basis) == (True, "BSD-2-Clause", "override+allow-list")
    assert not L.judge(pkg("othernum", "BSD"), POLICY).ok  # 'BSD' alone is not SPDX


@pytest.mark.parametrize("licence", ["", "   ", "See LICENSE file", "BSD"])
def test_missing_or_unparsable_licence_fails(licence: str) -> None:
    assert not L.judge(pkg("mystery", licence), POLICY).ok


# --- policy ---------------------------------------------------------------------------------------


def test_policy_is_the_documented_one() -> None:
    adr011 = {"MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC", "MPL-2.0", "Zlib"}
    lgpl = {"LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later"}
    td23 = {"Unlicense", "0BSD", "CC0-1.0", "PSF-2.0"}
    assert set(ALLOWED) == adr011 | lgpl | td23
    assert not [a for a in ALLOWED if "GPL" in a and not a.startswith("LGPL")]
    assert "EXT-07" in POLICY["status"]
    for e in POLICY["package_exceptions"]:
        assert e["reason"].strip() and e["status"] == "pending EXT-07"


def test_exception_without_reason_is_a_configuration_error(tmp_path: Path) -> None:
    bad = json.loads(json.dumps(POLICY))
    bad["package_exceptions"][0]["reason"] = " "
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    assert L.main(["--policy", str(path), "--inventory", str(inventory(tmp_path, CLEAN))]) == 2


# --- SOUP list ------------------------------------------------------------------------------------


def test_soup_list_is_sorted_complete_and_deterministic(tmp_path: Path) -> None:
    soup = tmp_path / "soup.csv"
    inv = inventory(tmp_path, list(reversed(CLEAN)))
    assert L.main(["--inventory", str(inv), "--soup", str(soup)]) == 0
    first = soup.read_bytes()
    assert L.main(["--inventory", str(inv), "--soup", str(soup)]) == 0
    assert soup.read_bytes() == first
    rows = first.decode().splitlines()
    assert rows[0] == "ecosystem,component,name,version,licence,supplier,basis"
    assert (
        len(rows) == 1 + len(CLEAN) and rows[1].startswith("npm,") and rows[-1].startswith("pypi,")
    )


@pytest.mark.parametrize(
    ("candidates", "name"),
    [
        (("Mike Bayer <mike@example.org>",), "Mike Bayer"),
        ((None, "Jane Roe <jane@example.org>, john@example.org"), "Jane Roe"),
        (("", None, "Team X"), "Team X"),
        (("x@example.org",), ""),
    ],
)
def test_supplier_names_drop_email_addresses(candidates: tuple[str | None, ...], name: str) -> None:
    assert L.supplier_name(*candidates) == name
