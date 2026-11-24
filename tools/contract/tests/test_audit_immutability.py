"""CI-FN-AUD-06 / TC-FR-121 / TC-SEC-03: no mutate path for the audit log in API, UI or code.

TT-C completion (IMPLEMENTATION_PLAN §5.2, DoD-C): the clean tree passes; each seeded violation
fails the check and is named. Nothing in the repository tree is modified: seeds are copies of
the contract, apps built in the test, or files in a temporary directory.
Database side (application roles, triggers): services/api/tests/integration/
test_audit_immutability_db.py.
"""

import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

from fastapi import FastAPI
import pytest

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[3]


def _load() -> ModuleType:
    path = ROOT / "tools/contract/audit_immutability.py"
    spec = importlib.util.spec_from_file_location("audit_immutability_check", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["audit_immutability_check"] = mod
    spec.loader.exec_module(mod)
    return mod


ai = _load()


def _contract() -> dict[str, Any]:
    return json.loads(ai.OPENAPI.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


OP = {"responses": {"200": {"description": "seeded"}}}


# --- clean tree -------------------------------------------------------------------------------


def test_completion_criterion_clean_tree_passes() -> None:
    """No mutate endpoint for the log exists; every mutate request answers 403/404/405."""
    app: FastAPI = ai.shipped_app()
    assert ai.api_problems(_contract()) == []
    assert ai.route_problems(app) == []
    assert ai.probe_problems(app) == []
    assert ai.code_problems() == []
    assert ai.main([]) == 0


def test_code_scan_sees_the_shipped_sources() -> None:
    files = {p.relative_to(ROOT).as_posix() for p in ai.code_files(ROOT)}
    assert "services/api/src/jude_api/platform/aud.py" in files
    assert "services/worker/src/jude_worker/__init__.py" in files
    assert not any("/migrations/" in f for f in files)  # grants and triggers live there


def test_probe_covers_the_planned_audit_endpoints() -> None:
    paths = ai.probe_paths(ai.shipped_app())
    assert {"/api/v1/audit", "/api/v1/audit/1", "/api/v1/audit.csv"} <= set(paths)


# --- 1. OpenAPI: seeded violations -----------------------------------------------------------


@pytest.mark.parametrize("method", ["put", "patch", "delete", "post"])
@pytest.mark.parametrize("path", ["/api/v1/audit/{seq}", "/api/v1/audit", "/api/v1/audit.csv"])
def test_seeded_mutate_operation_in_contract_fails(method: str, path: str) -> None:
    doc = copy.deepcopy(_contract())
    doc["paths"].setdefault(path, {})[method] = OP
    assert ai.api_problems(doc) == [
        f"openapi: {method.upper()} {path}: audit log entries must not be changed through the API"
    ]


def test_seeded_nested_audit_path_fails() -> None:
    doc = copy.deepcopy(_contract())
    doc["paths"]["/api/v1/cases/{case_id}/audit-log/{seq}"] = {"delete": OP}
    assert len(ai.api_problems(doc)) == 1


def test_reads_and_the_append_only_verify_are_allowed() -> None:
    doc = copy.deepcopy(_contract())
    doc["paths"]["/api/v1/audit"] = {"get": OP}
    doc["paths"]["/api/v1/audit.csv"] = {"get": OP}
    doc["paths"]["/api/v1/audit/verify"] = {"post": OP}
    doc["paths"]["/api/v1/authority/{id}"] = {"delete": OP}  # not an audit path
    assert ai.api_problems(doc) == []


def test_seeded_contract_makes_the_cli_fail(tmp_path: Path, capsys: Any) -> None:
    doc = copy.deepcopy(_contract())
    doc["paths"]["/api/v1/audit/{seq}"] = {"patch": OP}
    seeded = tmp_path / "openapi.json"
    seeded.write_text(json.dumps(doc), encoding="utf-8")
    assert ai.main(["--openapi", str(seeded)]) == 1
    assert "AUDIT-IMMUTABILITY openapi: PATCH /api/v1/audit/{seq}" in capsys.readouterr().out


# --- 2./3. live routes and HTTP probe: seeded violations --------------------------------------


def _seeded_app(include_in_schema: bool) -> FastAPI:
    app: FastAPI = ai.shipped_app()

    @app.get("/api/v1/audit")
    def view() -> list[int]:
        return []

    @app.delete("/api/v1/audit/{seq}", include_in_schema=include_in_schema)
    def erase(seq: int) -> None:
        return None

    return app


@pytest.mark.parametrize("include_in_schema", [True, False])
def test_seeded_delete_route_fails_even_when_hidden_from_the_schema(
    include_in_schema: bool,
) -> None:
    app = _seeded_app(include_in_schema)
    assert ai.route_problems(app) == [
        "route: DELETE /api/v1/audit/{seq}: audit log entries must not be changed through the API"
    ]
    found = ai.probe_problems(app)
    assert "probe: DELETE /api/v1/audit/1 answered 200 (expected 403/404/405)" in found
    assert all(p.startswith("probe: DELETE /api/v1/audit/") for p in found)


def test_read_only_audit_route_answers_405_to_mutations() -> None:
    app: FastAPI = ai.shipped_app()

    @app.get("/api/v1/audit/{seq}")
    def one(seq: int) -> int:
        return seq

    assert ai.route_problems(app) == []
    assert ai.probe_problems(app) == []


# --- 4. shipped code: seeded violations -------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE audit.audit_event SET type = %s",
        'update "audit".audit_summary set summary_after = null',
        "DELETE FROM audit.audit_event WHERE seq = %s",
        "DELETE\n  FROM ONLY audit.audit_summary",
        "TRUNCATE audit.audit_event CASCADE",
        "TRUNCATE TABLE audit.chain_head",
        "UPDATE audit.chain_head SET last_seq = 0",
        "ALTER TABLE audit.audit_event DISABLE TRIGGER ALL",
        "DROP TABLE IF EXISTS audit.audit_event",
        "GRANT UPDATE ON audit.audit_event TO app_rw",
        "SET session_replication_role = replica",
    ],
)
def test_seeded_sql_in_shipped_code_fails(tmp_path: Path, sql: str) -> None:
    src = tmp_path / "services/api/src/jude_api"
    src.mkdir(parents=True)
    (src / "seeded.py").write_text(f'QUERY = """{sql}"""\n', encoding="utf-8")
    found = ai.code_problems(tmp_path)
    assert len(found) == 1
    assert found[0].startswith("code: services/api/src/jude_api/seeded.py:1: ")


def test_sql_in_migrations_and_reads_are_not_flagged(tmp_path: Path) -> None:
    mig = tmp_path / "services/api/src/jude_api/migrations/versions"
    mig.mkdir(parents=True)
    (mig / "0001.py").write_text('X = "UPDATE audit.chain_head SET last_seq = 1"\n')
    web = tmp_path / "apps/web/src"
    web.mkdir(parents=True)
    (web / "audit.ts").write_text('const q = "SELECT * FROM audit.audit_event";\n')
    (web / "page.tsx").write_text("// update the audit view\n")
    assert ai.code_problems(tmp_path) == []
