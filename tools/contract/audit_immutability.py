"""Audit immutability check (TSK-AUD-06-C, FN-AUD-06; FR-121, SEC-03; CI-FN-AUD-06).

    python tools/contract/audit_immutability.py [--openapi PATH]
    python tools/contract/audit_immutability.py --db-url URL [--app-login NAME ...]

Log entries must not be editable or deletable through the UI, the API or the application
database roles. The UI reaches data only through the API: the proxy routes /api/* to FastAPI
and everything else to Next.js, whose only route handler is /healthz. So the check covers:

1. **OpenAPI** (contract of record, ``packages/contracts/openapi.json``): an ``/audit*`` path
   offers no PUT, PATCH or DELETE, and POST only where APPEND_ONLY_POSTS allows it.
2. **Live routes** of the app, including routes hidden from the schema: the same rule.
3. **HTTP probe**: PUT, PATCH, DELETE (and POST where not allowed) on the audit paths answer
   403, 404 or 405, never a success or a validation error.
4. **Shipped code** (``services/*/src``, ``packages/*/src``, ``apps/web/src``, migrations
   excluded): no SQL that updates, deletes, truncates, alters or re-grants an ``audit.*`` table,
   and no ``session_replication_role`` (it turns triggers off).
5. **Database** (``--db-url``; the integration stage calls ``db_problems``): no application
   role, no named login and not PUBLIC holds UPDATE, DELETE, TRUNCATE or column UPDATE on any
   ``audit`` table, or membership in its owner; the append-only triggers on ``audit_event`` are
   enabled for UPDATE, DELETE and TRUNCATE; the only SECURITY DEFINER function in ``audit`` is
   ``append_event``, with a pinned search_path and EXECUTE for ``audit_append`` alone.

The contract stage runs checks 1-4; the integration stage runs check 5 on a fresh database.
Exit 1 and one ``AUDIT-IMMUTABILITY`` line per problem when anything is found.
"""

import argparse
from collections.abc import Iterable, Mapping, Sequence
import json
from pathlib import Path
import re
import sys
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg

from jude_api.main import create_app
from jude_api.platform.iam import api_routes

Conn = psycopg.Connection[Any]

ROOT = Path(__file__).resolve().parents[2]
OPENAPI = ROOT / "packages/contracts/openapi.json"
API_PREFIX = "/api/v1"

# POST on an audit path is allowed only when it appends and never changes an entry.
APPEND_ONLY_POSTS: Mapping[str, str] = {
    "/api/v1/audit/verify": "FN-AUD-03: recomputes the chain and appends audit.verified",
}
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
PROBE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
PROBE_PATHS = (
    "/api/v1/audit",
    "/api/v1/audit/1",
    "/api/v1/audit/events/1",
    "/api/v1/audit.csv",
    "/api/v1/audit/verify",
    "/api/v1/audit/chain_head",
)
PROBE_OK = frozenset({403, 404, 405})

CODE_ROOTS = ("services/*/src", "packages/*/src", "apps/web/src")
CODE_SUFFIXES = frozenset({".py", ".sql", ".ts", ".tsx", ".js", ".mjs"})
CODE_EXCLUDED_DIRS = frozenset({"migrations", "node_modules", "__pycache__", ".next"})
_T = r'(?:ONLY\s+)?"?audit"?\s*\.'
CODE_PATTERNS = (
    re.compile(rf"\bUPDATE\s+{_T}", re.IGNORECASE),
    re.compile(rf"\bDELETE\s+FROM\s+{_T}", re.IGNORECASE),
    re.compile(rf"\bTRUNCATE\s+(?:TABLE\s+)?{_T}", re.IGNORECASE),
    re.compile(rf"\b(?:ALTER|DROP)\s+TABLE\s+(?:IF\s+EXISTS\s+)?{_T}", re.IGNORECASE),
    re.compile(rf"\b(?:GRANT|REVOKE)\b[^;]*?\bON\s+(?:TABLE\s+)?{_T}", re.IGNORECASE),
    re.compile(r"\bsession_replication_role\b", re.IGNORECASE),
)

APP_ROLES = ("app_rw", "worker_rw", "audit_append", "admin_ro")
MUTATE_PRIVILEGES = ("UPDATE", "DELETE", "TRUNCATE")
SECURITY_DEFINER_ALLOWED = frozenset({"append_event"})
APPEND_EXECUTORS = frozenset({"audit_append"})
APPEND_ONLY_TABLE = "audit_event"
TRIGGER_FUNCTION = "forbid_change"
# pg_trigger.tgtype bits (src/include/catalog/pg_trigger.h)
TG_BEFORE, TG_DELETE, TG_UPDATE, TG_TRUNCATE = 1 << 1, 1 << 3, 1 << 4, 1 << 5


def is_audit_path(path: str) -> bool:
    return any(segment.startswith("audit") for segment in path.split("/"))


def method_problem(method: str, path: str) -> str | None:
    method = method.upper()
    if not is_audit_path(path) or method in READ_METHODS:
        return None
    if method == "POST" and path in APPEND_ONLY_POSTS:
        return None
    return f"{method} {path}: audit log entries must not be changed through the API"


# --- 1. OpenAPI -------------------------------------------------------------------------------


def api_problems(doc: Mapping[str, Any]) -> list[str]:
    out = []
    for path, item in sorted(doc.get("paths", {}).items()):
        for method in sorted(item):
            if method in ("parameters", "summary", "description", "servers"):
                continue
            problem = method_problem(method, path)
            if problem:
                out.append(f"openapi: {problem}")
    return out


# --- 2. live routes and 3. HTTP probe ---------------------------------------------------------


def shipped_app() -> FastAPI:
    return create_app(db_check=lambda: None, readiness_checks={})


def route_problems(app: FastAPI) -> list[str]:
    out = []
    for method, path, _ in api_routes(app):
        problem = method_problem(method, path)
        if problem:
            out.append(f"route: {problem}")
    return sorted(set(out))


def probe_paths(app: FastAPI) -> list[str]:
    paths = set(PROBE_PATHS)
    for _, path, _ in api_routes(app):
        if path.startswith(API_PREFIX) and is_audit_path(path):
            paths.add(re.sub(r"\{[^}]+\}", "1", path))
    return sorted(paths)


def probe_problems(app: FastAPI) -> list[str]:
    out = []
    with TestClient(app, raise_server_exceptions=False) as client:
        for path in probe_paths(app):
            for method in PROBE_METHODS:
                if method == "POST" and path in APPEND_ONLY_POSTS:
                    continue
                status = client.request(method, path, json={}).status_code
                if status not in PROBE_OK:
                    out.append(f"probe: {method} {path} answered {status} (expected 403/404/405)")
    return out


# --- 4. shipped code --------------------------------------------------------------------------


def code_files(root: Path) -> Iterable[Path]:
    for pattern in CODE_ROOTS:
        for base in sorted(root.glob(pattern)):
            for path in sorted(base.rglob("*")):
                if (
                    path.is_file()
                    and path.suffix in CODE_SUFFIXES
                    and not CODE_EXCLUDED_DIRS & set(path.relative_to(root).parts)
                ):
                    yield path


def code_problems(root: Path = ROOT) -> list[str]:
    out = []
    for path in code_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in CODE_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                rel = path.relative_to(root).as_posix()
                snippet = " ".join(match.group(0).split())
                out.append(f"code: {rel}:{line}: '{snippet}' changes the audit schema or log")
    return out


# --- 5. database ------------------------------------------------------------------------------


def db_problems(conn: Conn, logins: Sequence[str] = ()) -> list[str]:
    """Catalogue check on a migrated database. ``logins`` are the deployment's API login roles
    (members of app_rw and audit_append); they are checked like the group roles."""
    out: list[str] = []
    roles = [*APP_ROLES, *logins]
    for login in logins:
        row = conn.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s", (login,)
        ).fetchone()
        if row is None:
            out.append(f"db: login {login} does not exist")
        elif row[0]:
            out.append(f"db: login {login} is a superuser and can change the log")
    tables = conn.execute(
        "SELECT c.relname, c.relowner::regrole::text FROM pg_class c"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'audit' AND c.relkind IN ('r', 'p') ORDER BY c.relname"
    ).fetchall()
    if not any(name == APPEND_ONLY_TABLE for name, _ in tables):
        out.append(f"db: audit.{APPEND_ONLY_TABLE} is missing")
    for name, owner in tables:
        table = f"audit.{name}"
        for role in [*roles, "public"]:
            for privilege in MUTATE_PRIVILEGES:
                if _flag(conn, "has_table_privilege(%s, %s, %s)", (role, table, privilege)):
                    out.append(f"db: {role} has {privilege} on {table}")
            if _flag(conn, "has_any_column_privilege(%s, %s, 'UPDATE')", (role, table)):
                if not _flag(conn, "has_table_privilege(%s, %s, 'UPDATE')", (role, table)):
                    out.append(f"db: {role} has column UPDATE on {table}")
            if role != "public" and _flag(conn, "pg_has_role(%s, %s, 'MEMBER')", (role, owner)):
                out.append(f"db: {role} is the owner of {table} or a member of it ({owner})")
    out += _trigger_problems(conn)
    out += _function_problems(conn, APP_ROLES)
    return out


def _flag(conn: Conn, expr: str, params: tuple[str, ...]) -> bool:
    row = conn.execute(f"SELECT {expr}", params).fetchone()
    return bool(row and row[0])


def _trigger_problems(conn: Conn) -> list[str]:
    rows = conn.execute(
        "SELECT t.tgtype FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid"
        " JOIN pg_namespace pn ON pn.oid = p.pronamespace"
        " WHERE t.tgrelid = to_regclass(%s) AND NOT t.tgisinternal"
        " AND t.tgenabled IN ('O', 'A') AND pn.nspname = 'audit' AND p.proname = %s",
        (f"audit.{APPEND_ONLY_TABLE}", TRIGGER_FUNCTION),
    ).fetchall()
    covered = 0
    for (tgtype,) in rows:
        if tgtype & TG_BEFORE:
            covered |= tgtype & (TG_DELETE | TG_UPDATE | TG_TRUNCATE)
    out = []
    for bit, op in ((TG_UPDATE, "UPDATE"), (TG_DELETE, "DELETE"), (TG_TRUNCATE, "TRUNCATE")):
        if not covered & bit:
            out.append(
                f"db: no enabled BEFORE {op} trigger audit.{TRIGGER_FUNCTION} on"
                f" audit.{APPEND_ONLY_TABLE}"
            )
    return out


def _function_problems(conn: Conn, roles: Sequence[str]) -> list[str]:
    out = []
    rows = conn.execute(
        "SELECT p.oid::regprocedure::text, p.proname, p.proconfig FROM pg_proc p"
        " JOIN pg_namespace n ON n.oid = p.pronamespace"
        " WHERE n.nspname = 'audit' AND p.prosecdef ORDER BY 1"
    ).fetchall()
    for signature, name, config in rows:
        if name not in SECURITY_DEFINER_ALLOWED:
            out.append(f"db: {signature} is SECURITY DEFINER (only append_event may be)")
            continue
        if not any(c.startswith("search_path=") for c in config or ()):
            out.append(f"db: {signature} has no pinned search_path")
        for role in [*roles, "public"]:
            if role not in APPEND_EXECUTORS and _flag(
                conn, "has_function_privilege(%s, %s, 'EXECUTE')", (role, signature)
            ):
                out.append(f"db: {role} may EXECUTE {signature} (only audit_append)")
    return out


# --- CLI --------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--openapi", type=Path, default=OPENAPI)
    parser.add_argument("--db-url", help="check this database instead of the API and code")
    parser.add_argument("--app-login", action="append", default=[], help="API login role")
    args = parser.parse_args(argv)
    if args.db_url:
        with psycopg.connect(args.db_url) as conn:
            found = db_problems(conn, args.app_login)
    else:
        doc = json.loads(args.openapi.read_text(encoding="utf-8"))
        app = shipped_app()
        found = api_problems(doc) + route_problems(app) + probe_problems(app) + code_problems()
    for problem in found:
        print(f"AUDIT-IMMUTABILITY {problem}")
    if found:
        return 1
    print("audit immutability: no path changes a log entry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
