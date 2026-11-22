"""Contract compatibility rules (XC-FND-06): every breaking change is caught, additions pass."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[3]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("oacompat", ROOT / "tools/contract/oacompat.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["oacompat"] = mod
    spec.loader.exec_module(mod)
    return mod


oa = _load()


def base() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/api/v1/cases/{case_id}": {
                "parameters": [
                    {
                        "in": "path",
                        "name": "case_id",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "get": {
                    "operationId": "get_case",
                    "parameters": [
                        {
                            "in": "query",
                            "name": "view",
                            "required": False,
                            "schema": {"enum": ["full", "brief"], "type": "string"},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Case"}
                                }
                            },
                        },
                        "default": {
                            "description": "err",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            },
                        },
                    },
                },
                "patch": {
                    "operationId": "patch_case",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CasePatch"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Case"}
                                }
                            },
                        }
                    },
                },
            }
        },
        "components": {
            "schemas": {
                "Case": {
                    "type": "object",
                    "required": ["id", "status", "tags"],
                    "properties": {
                        "id": {"type": "string"},
                        "status": {"type": "string", "enum": ["draft", "approved"]},
                        "note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "created_at": {"type": "string", "format": "date-time"},
                    },
                },
                "CasePatch": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["version"],
                    "properties": {
                        "version": {"type": "integer", "minimum": 1},
                        "note": {"type": "string", "maxLength": 500},
                        "status": {"type": "string", "enum": ["draft", "approved"]},
                    },
                },
                "Error": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {"error": {"type": "string"}},
                },
            }
        },
    }


def findings(mutate: Any) -> list[str]:
    old = base()
    new = copy.deepcopy(old)
    mutate(new)
    return [str(f) for f in oa.breaking_changes(old, new)]


S = "components"


def _schemas(d: dict[str, Any]) -> dict[str, Any]:
    return d[S]["schemas"]  # type: ignore[no-any-return]


def _get(d: dict[str, Any]) -> dict[str, Any]:
    return d["paths"]["/api/v1/cases/{case_id}"]["get"]  # type: ignore[no-any-return]


BREAKING = {
    "path removed": lambda d: d["paths"].clear(),
    "operation removed": lambda d: d["paths"]["/api/v1/cases/{case_id}"].pop("patch"),
    "parameter removed": lambda d: _get(d)["parameters"].clear(),
    "parameter newly required": lambda d: _get(d)["parameters"][0].update(required=True),
    "new required parameter": lambda d: _get(d)["parameters"].append(
        {"in": "header", "name": "If-Match", "required": True, "schema": {"type": "string"}}
    ),
    "param enum narrowed": lambda d: _get(d)["parameters"][0]["schema"].update(enum=["full"]),
    "response status removed": lambda d: _get(d)["responses"].pop("default"),
    "media type removed": lambda d: _get(d)["responses"]["200"]["content"].clear(),
    "response field removed": lambda d: _schemas(d)["Case"]["properties"].pop("created_at"),
    "response field no longer required": lambda d: _schemas(d)["Case"]["required"].remove("tags"),
    "response type widened (nullable)": lambda d: _schemas(d)["Case"]["properties"].update(
        id={"anyOf": [{"type": "string"}, {"type": "null"}]}
    ),
    "response type changed": lambda d: _schemas(d)["Case"]["properties"].update(
        id={"type": "integer"}
    ),
    "response enum value added": lambda d: _schemas(d)["Case"]["properties"]["status"][
        "enum"
    ].append("exported"),
    "response array item type changed": lambda d: _schemas(d)["Case"]["properties"]["tags"].update(
        items={"type": "integer"}
    ),
    "response format changed": lambda d: _schemas(d)["Case"]["properties"]["created_at"].update(
        format="date"
    ),
    "error envelope field removed": lambda d: _schemas(d)["Error"]["properties"].clear(),
    "new required request field": lambda d: _schemas(d)["CasePatch"]["required"].append("note"),
    "request type narrowed": lambda d: _schemas(d)["CasePatch"]["properties"].update(
        note={"type": "integer"}
    ),
    "request enum value removed": lambda d: _schemas(d)["CasePatch"]["properties"]["status"].update(
        enum=["draft"]
    ),
    "request maxLength lowered": lambda d: _schemas(d)["CasePatch"]["properties"]["note"].update(
        maxLength=100
    ),
    "request minimum raised": lambda d: _schemas(d)["CasePatch"]["properties"]["version"].update(
        minimum=2
    ),
    "request pattern added": lambda d: _schemas(d)["CasePatch"]["properties"]["note"].update(
        pattern="^[a-z]+$"
    ),
    "request field removed (extra forbidden)": lambda d: _schemas(d)["CasePatch"]["properties"].pop(
        "note"
    ),
    "request body newly required": lambda d: _get(d).update(
        requestBody={"required": True, "content": {"application/json": {"schema": {}}}}
    ),
}

ADDITIVE = {
    "new path": lambda d: d["paths"].update({"/api/v1/jobs": {"get": {"responses": {}}}}),
    "new operation": lambda d: d["paths"]["/api/v1/cases/{case_id}"].update(
        delete={"responses": {"204": {"description": "gone"}}}
    ),
    "new optional parameter": lambda d: _get(d)["parameters"].append(
        {"in": "query", "name": "page", "required": False, "schema": {"type": "integer"}}
    ),
    "new response field": lambda d: _schemas(d)["Case"]["properties"].update(
        owner={"type": "string"}
    ),
    "response field becomes required": lambda d: _schemas(d)["Case"]["required"].append("note"),
    "response enum value removed": lambda d: _schemas(d)["Case"]["properties"]["status"].update(
        enum=["draft"]
    ),
    "response type narrowed (not null)": lambda d: _schemas(d)["Case"]["properties"].update(
        note={"type": "string"}
    ),
    "new response status": lambda d: _get(d)["responses"].update({"404": {"description": "x"}}),
    "new optional request field": lambda d: _schemas(d)["CasePatch"]["properties"].update(
        label={"type": "string"}
    ),
    "request enum value added": lambda d: _schemas(d)["CasePatch"]["properties"]["status"][
        "enum"
    ].append("archived"),
    "request maxLength raised": lambda d: _schemas(d)["CasePatch"]["properties"]["note"].update(
        maxLength=1000
    ),
    "request type widened": lambda d: _schemas(d)["CasePatch"]["properties"].update(
        note={"anyOf": [{"type": "string"}, {"type": "null"}]}
    ),
    "description changed": lambda d: _get(d)["responses"]["200"].update(description="changed"),
}


def test_identical_documents_are_compatible() -> None:
    assert oa.breaking_changes(base(), base()) == []


@pytest.mark.parametrize("name", sorted(BREAKING))
def test_breaking_change_is_caught(name: str) -> None:
    assert findings(BREAKING[name]), f"{name} was not flagged"


@pytest.mark.parametrize("name", sorted(ADDITIVE))
def test_additive_change_passes(name: str) -> None:
    assert findings(ADDITIVE[name]) == []


def test_cli_exit_codes(tmp_path: Path) -> None:
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    old.write_text(json.dumps(base()), encoding="utf-8")
    broken = base()
    broken["paths"].clear()
    new.write_text(json.dumps(broken), encoding="utf-8")
    assert oa.main([str(old), str(old)]) == 0
    assert oa.main([str(old), str(new)]) == 1
    assert oa.main([str(new), str(old)]) == 0  # adding the path back is additive


def test_base_ref_missing_file_passes_and_bad_ref_errors() -> None:
    assert oa.main(["--base-ref", "HEAD", "no/such/file.json"]) == 0
    assert oa.main(["--base-ref", "no-such-ref-xyz", "packages/contracts/openapi.json"]) == 2


def test_real_contract_is_compatible_with_itself() -> None:
    doc = json.loads((ROOT / "packages/contracts/openapi.json").read_text(encoding="utf-8"))
    assert oa.breaking_changes(doc, doc) == []
    contract = str(ROOT / "packages/contracts/openapi.json")
    proc = subprocess.run(  # noqa: S603 — fixed argv
        [sys.executable, str(ROOT / "tools/contract/oacompat.py"), contract, contract],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
