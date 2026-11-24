"""CI-FN-AUD-06 / TC-FR-121 / TC-SEC-03: the application database role cannot change the log.

Completion criterion (TSK-AUD-06-C): UPDATE as the application role raises a permission error.
The application role is checked the way a deployment sets it up: a LOGIN role that is a member
of app_rw and audit_append (SCHEMA.md), working as app_rw and appending through the audit
service. TT-C: the migrated database passes the catalogue check; each seeded violation (a grant,
a disabled trigger, an extra SECURITY DEFINER function, ...) fails it. Every seed is rolled back.
All rows are synthetic.
"""

from collections.abc import Iterator
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Any
import uuid

import psycopg
from psycopg import errors, sql
import pytest

from jude_api.platform import aud

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[Any, ...]]
ROOT = Path(__file__).resolve().parents[4]


def _load() -> ModuleType:
    path = ROOT / "tools/contract/audit_immutability.py"
    spec = importlib.util.spec_from_file_location("audit_immutability_db_check", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["audit_immutability_db_check"] = mod
    spec.loader.exec_module(mod)
    return mod


ai = _load()

MUTATIONS = (
    "UPDATE audit.audit_event SET type = 'case.created'",
    "UPDATE audit.audit_event SET user_id = NULL",
    "DELETE FROM audit.audit_event",
    "TRUNCATE audit.audit_event",
    "UPDATE audit.audit_summary SET summary_after = NULL",
    "DELETE FROM audit.audit_summary",
    "TRUNCATE audit.audit_summary",
    "UPDATE audit.chain_head SET last_seq = 0, last_hash = NULL",
    "DELETE FROM audit.chain_head",
    "INSERT INTO audit.chain_head (id, last_seq) VALUES (false, 0)",
)


@pytest.fixture
def api_login(conn: Conn) -> Iterator[str]:
    """A deployment-like API login (LOGIN, member of app_rw + audit_append), in the test's
    transaction: the role and everything else is rolled back afterwards."""
    name = f"jude_it_api_{uuid.uuid4().hex[:8]}"
    conn.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(name)))
    conn.execute(sql.SQL("GRANT app_rw, audit_append TO {}").format(sql.Identifier(name)))
    yield name


def refused(conn: Conn, statement: str, error: type[Exception]) -> None:
    with pytest.raises(error), conn.transaction():
        conn.execute(statement)


def append_two(conn: Conn) -> None:
    for i in (1, 2):
        aud.append(conn, aud.AuditEvent(
            "case.created", None, "system", object_type="case", object_id=f"J-0000000{i}",
            summary_after={"status": "active"},
        ))  # fmt: skip


def test_completion_criterion_app_role_update_raises_permission_error(
    conn: Conn, api_login: str
) -> None:
    conn.execute(sql.SQL("SET SESSION AUTHORIZATION {}").format(sql.Identifier(api_login)))
    conn.execute("SET ROLE app_rw")  # as the API works (deps.APP_ROLE)
    append_two(conn)  # the API login appends through the audit service ...
    for role in ("app_rw", "audit_append", "NONE"):  # ... and changes nothing, in any role
        conn.execute(f"SET ROLE {role}")
        for statement in MUTATIONS:
            refused(conn, statement, errors.InsufficientPrivilege)
    conn.execute("RESET SESSION AUTHORIZATION")
    assert aud.verify(conn) == aud.Verification(2, None)
    assert conn.execute("SELECT count(*) FROM audit.audit_summary").fetchone() == (2,)


def test_clean_database_passes_the_catalogue_check(conn: Conn, api_login: str) -> None:
    assert ai.db_problems(conn, [api_login]) == []


def test_cli_checks_a_database(migrated_url: str, capsys: Any) -> None:
    assert ai.main(["--db-url", migrated_url]) == 0
    assert "no path changes a log entry" in capsys.readouterr().out


SEEDS = [
    pytest.param(
        "GRANT UPDATE ON audit.audit_event TO app_rw",
        "db: app_rw has UPDATE on audit.audit_event",
        id="grant-update-core",
    ),
    pytest.param(
        "GRANT DELETE ON audit.audit_summary TO audit_append",
        "db: audit_append has DELETE on audit.audit_summary",
        id="grant-delete-summary",
    ),
    pytest.param(
        "GRANT TRUNCATE ON audit.chain_head TO PUBLIC",
        "db: public has TRUNCATE on audit.chain_head",
        id="grant-truncate-public",
    ),
    pytest.param(
        "GRANT UPDATE (summary_after) ON audit.audit_summary TO app_rw",
        "db: app_rw has column UPDATE on audit.audit_summary",
        id="grant-column-update",
    ),
    pytest.param(
        "GRANT UPDATE ON audit.chain_head TO admin_ro",
        "db: admin_ro has UPDATE on audit.chain_head",
        id="grant-update-head",
    ),
    pytest.param(
        "ALTER TABLE audit.audit_summary OWNER TO worker_rw",
        "db: worker_rw is the owner of audit.audit_summary or a member of it (worker_rw)",
        id="owner-is-app-role",
    ),
    pytest.param(
        "ALTER TABLE audit.audit_event DISABLE TRIGGER audit_event_no_update_delete",
        "db: no enabled BEFORE UPDATE trigger audit.forbid_change on audit.audit_event",
        id="trigger-disabled",
    ),
    pytest.param(
        "DROP TRIGGER audit_event_no_truncate ON audit.audit_event",
        "db: no enabled BEFORE TRUNCATE trigger audit.forbid_change on audit.audit_event",
        id="trigger-dropped",
    ),
    pytest.param(
        "CREATE FUNCTION audit.reset_head() RETURNS void LANGUAGE sql SECURITY DEFINER"
        " AS 'UPDATE audit.chain_head SET last_seq = 0'",
        "db: audit.reset_head() is SECURITY DEFINER (only append_event may be)",
        id="extra-security-definer",
    ),
    pytest.param(
        "ALTER FUNCTION audit.append_event RESET search_path",
        "has no pinned search_path",
        id="search-path-unpinned",
    ),
    pytest.param(
        "GRANT EXECUTE ON FUNCTION audit.append_event TO PUBLIC",
        "db: public may EXECUTE audit.append_event(",
        id="append-for-public",
    ),
]


@pytest.mark.parametrize(("seed", "expected"), SEEDS)
def test_seeded_violation_fails_the_catalogue_check(
    conn: Conn, api_login: str, seed: str, expected: str
) -> None:
    with conn.transaction(force_rollback=True):
        conn.execute(seed)
        found = ai.db_problems(conn, [api_login])
    assert any(expected in p for p in found), found
    assert ai.db_problems(conn, [api_login]) == []  # the seed is gone again


def test_seeded_superuser_login_fails(conn: Conn, api_login: str) -> None:
    conn.execute(sql.SQL("ALTER ROLE {} SUPERUSER").format(sql.Identifier(api_login)))
    found = ai.db_problems(conn, [api_login])
    assert f"db: login {api_login} is a superuser and can change the log" in found


def test_trigger_still_refuses_when_a_grant_slips_through(conn: Conn) -> None:
    """Defence in depth: with a seeded UPDATE grant, the append-only trigger still refuses."""
    conn.execute("SET ROLE app_rw")
    append_two(conn)
    conn.execute("RESET ROLE")
    conn.execute("GRANT USAGE ON SCHEMA audit TO app_rw")
    conn.execute("GRANT SELECT, UPDATE, DELETE ON audit.audit_event TO app_rw")
    conn.execute("SET ROLE app_rw")
    refused(conn, "UPDATE audit.audit_event SET type = 'case.created'", errors.RaiseException)
    refused(conn, "DELETE FROM audit.audit_event", errors.RaiseException)
