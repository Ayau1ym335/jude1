"""FN-IAM-04 Authorise request: permission matrix + case scope (TSK-IAM-04-A; FR-130, SEC-02).

- ``permissions.yaml`` is the single role x action table. A route declares its action with
  ``who: Annotated[Requester, Depends(ActionCheck("FN-XXX-NN"))]``; a denied role gets
  403 ROLE_FORBIDDEN and an ``authz.denied`` audit event, committed before the refusal.
- ``assert_every_route_authorised`` (called by create_app): every /api/v1 route is either in
  the matrix's public list or declares a known action key; otherwise the application refuses to
  start (deny by default, FN-IAM-04 step 1 / error handling).
- ``case_access`` / ``ensure_case_writable``: case scope. In the single-clinic MVP every role
  that may read case contents (FN-CAS-02) sees every case; objects of an archived case are
  read-only for mutating actions -> 409 CASE_ARCHIVED (FR-003).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
import psycopg
import yaml

from jude_api.platform import aud
from jude_api.platform.deps import CurrentRequester, Db, Requester
from jude_api.platform.errors import ApiError
from jude_api.platform.iam import api_routes

MATRIX_PATH = Path(__file__).resolve().parent / "permissions.yaml"
CASE_READ = "FN-CAS-02"


@dataclass(frozen=True)
class Matrix:
    roles: tuple[str, ...]
    allow: Mapping[str, frozenset[str]]
    basis: Mapping[str, str]
    public: frozenset[tuple[str, str]]

    def allowed(self, role: str, action: str) -> bool:
        if action not in self.allow:
            raise KeyError(f"unknown action key {action!r}")
        return role in self.allow[action]


@cache
def matrix() -> Matrix:
    doc = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))
    if doc.get("schema") != "permissions/1":
        raise ValueError("permissions.yaml: schema must be permissions/1")
    roles = tuple(doc["roles"])
    allow: dict[str, frozenset[str]] = {}
    basis: dict[str, str] = {}
    for action, entry in doc["actions"].items():
        cells = frozenset(entry["allow"])
        if not cells <= set(roles):
            raise ValueError(f"permissions.yaml: {action} allows unknown roles")
        if entry["basis"] not in ("fs", "fr-130", "engineering"):
            raise ValueError(f"permissions.yaml: {action} has no valid basis")
        allow[action], basis[action] = cells, entry["basis"]
    public = frozenset((m.upper(), p) for m, p in doc["public"])
    return Matrix(roles, allow, basis, public)


class ActionCheck:
    """Route dependency: the requester's role must be allowed ``action``."""

    def __init__(self, action: str) -> None:
        if action not in matrix().allow:
            raise KeyError(f"route declares unknown action key {action!r}")
        self.action = action

    def __call__(self, who: CurrentRequester, conn: Db) -> Requester:
        if matrix().allowed(who.role, self.action):
            return who
        with conn.transaction():
            aud.append(conn, aud.AuditEvent(
                "authz.denied", who.user_id, who.role, object_type="action",
                object_id=self.action, ui_session_id=who.ui_session_id,
            ))  # fmt: skip
        raise ApiError("ROLE_FORBIDDEN")


def _actions(dependant: Dependant) -> list[str]:
    found = [d.call.action for d in dependant.dependencies if isinstance(d.call, ActionCheck)]
    for d in dependant.dependencies:
        found += _actions(d)
    return found


def assert_every_route_authorised(app: FastAPI, prefix: str = "/api/v1") -> None:
    """Deny by default: an /api/v1 route without an action key (and not public) cannot start."""
    m = matrix()
    problems = []
    for method, path, dependant in api_routes(app):
        if not path.startswith(prefix) or (method, path) in m.public:
            continue
        if not _actions(dependant):
            problems.append(f"{method} {path}")
    if problems:
        raise RuntimeError(f"routes without an action key: {', '.join(problems)}")


def case_access(who: Requester, case_id: str) -> bool:
    """Single-clinic case scope: any role allowed to read case contents sees every case."""
    return matrix().allowed(who.role, CASE_READ)


def ensure_case_writable(conn: psycopg.Connection[Any], case_id: str) -> None:
    """FR-003: objects of an archived case are read-only -> 409 CASE_ARCHIVED."""
    row = conn.execute(
        'SELECT status FROM clinical."case" WHERE case_id = %s', (case_id,)
    ).fetchone()
    if row is None:
        raise ApiError("NOT_FOUND")
    if row[0] == "archived":
        raise ApiError("CASE_ARCHIVED")
