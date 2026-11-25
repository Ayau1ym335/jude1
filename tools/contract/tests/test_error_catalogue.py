"""Error catalogue check (TSK-API-02-A): completion criterion and each failure mode."""

import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[3]


def _load() -> ModuleType:
    path = ROOT / "tools/contract/error_catalogue.py"
    spec = importlib.util.spec_from_file_location("error_catalogue_check", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["error_catalogue_check"] = mod
    spec.loader.exec_module(mod)
    return mod


ec = _load()


def _catalogue() -> dict[str, Any]:
    return json.loads((ROOT / ec.CATALOGUE).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _messages() -> dict[str, str]:
    return json.loads((ROOT / ec.MESSAGES).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_completion_criterion_every_spec_code_is_catalogued() -> None:
    """Every code used by any FS function (and named by RTM v0.3/v0.4) exists in error/1."""
    codes = _catalogue()["codes"]
    used = ec.spec_codes()
    assert len(used) >= 90
    assert sorted(set(used) - set(codes)) == []
    assert {"PRESCRIPTION_MISSING", "ZONE_OVERLAP_NOT_ALLOWED", "ZONE_CONTOUR_INVALID"} <= set(
        codes
    )
    assert ec.main([]) == 0


def test_catalogue_is_consistent() -> None:
    assert ec.consistency(_catalogue(), _messages()) == []


def test_non_codes_are_real_tokens_of_the_documents() -> None:
    text = (ROOT / ec.FS).read_text(encoding="utf-8")
    text += "".join((ROOT / p).read_text(encoding="utf-8") for p in ec.RTMS)
    present = ec.tokens(text)
    assert sorted(set(ec.NON_CODES) - present) == []  # the list does not rot
    assert not set(ec.NON_CODES) & set(_catalogue()["codes"])


def test_missing_spec_code_is_reported() -> None:
    cat = _catalogue()
    del cat["codes"]["PRESCRIPTION_MISSING"]
    problems = ec.coverage(cat)
    assert any(p.startswith("PRESCRIPTION_MISSING: used by FN-CAS-06") for p in problems)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda c, m: c["codes"]["VERSION_CONFLICT"].update(http_status=None), "needs a 4xx/5xx"),
        (lambda c, m: c["codes"]["VERSION_CONFLICT"].update(http_status=200), "needs a 4xx/5xx"),
        (lambda c, m: c["codes"]["NON_FINITE"].update(http_status=422), "only refusals"),
        (lambda c, m: c["codes"]["NON_FINITE"].update(kind="fatal"), "unknown kind"),
        (lambda c, m: m.pop("error.version_conflict"), "no Russian message"),
        (lambda c, m: m.update({"error.orphan": "x"}), "has no code"),
        (lambda c, m: c["codes"]["VERSION_CONFLICT"].update(message_key="x"), "message_key must"),
        (lambda c, m: c["codes"]["VERSION_CONFLICT"].update(sources=[]), "no source"),
        (lambda c, m: c.update(schema="error/2"), "schema must"),
    ],
)
def test_inconsistency_is_reported(mutate: Any, expected: str) -> None:
    cat, msgs = copy.deepcopy(_catalogue()), dict(_messages())
    mutate(cat, msgs)
    assert any(expected in p for p in ec.consistency(cat, msgs))


def test_raised_codes_are_found_in_source() -> None:
    src = "raise ApiError(\"PRESCRIPTION_MISSING\")\nerror_response('NOT_FOUND')\nApiError(code)"
    assert ec.RAISED.findall(src) == ["PRESCRIPTION_MISSING", "NOT_FOUND"]
    assert set(ec.raised_codes()) <= set(_catalogue()["codes"])


def test_stability_against_base() -> None:
    old = _catalogue()
    new = copy.deepcopy(old)
    assert ec.stability(old, new, "base") == []
    new["codes"]["BRAND_NEW_CODE"] = dict(old["codes"]["VERSION_CONFLICT"])  # additions are fine
    assert ec.stability(old, new, "base") == []
    del new["codes"]["LOGIN_TAKEN"]
    new["codes"]["VERSION_CONFLICT"]["http_status"] = 412
    new["codes"]["NON_FINITE"]["kind"] = "job"
    problems = ec.stability(old, new, "base")
    assert any(p.startswith("LOGIN_TAKEN: removed") for p in problems)
    assert any("VERSION_CONFLICT: http_status changed" in p for p in problems)
    assert any("NON_FINITE: kind changed" in p for p in problems)


def test_drafts_before_error_1_do_not_bind() -> None:
    assert ec.main(["--base-ref", "HEAD"]) == 0


def test_only_a_frozen_base_binds(monkeypatch: pytest.MonkeyPatch) -> None:
    draft = dict(_catalogue(), status="draft: frozen at M0 exit after engineering-lead sign-off")
    frozen = dict(draft, status="frozen 2026-12-01 (engineering lead, IDR-05)")

    class Proc:
        returncode = 0
        stderr = ""

        def __init__(self, doc: dict[str, Any]) -> None:
            self.stdout = json.dumps(doc)

    monkeypatch.setattr(ec.subprocess, "run", lambda *a, **k: Proc(draft))
    assert ec._at_ref("base", ec.CATALOGUE) is None
    monkeypatch.setattr(ec.subprocess, "run", lambda *a, **k: Proc(frozen))
    assert ec._at_ref("base", ec.CATALOGUE) == frozen
