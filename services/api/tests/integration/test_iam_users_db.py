"""IT-FN-IAM-05: manage user accounts, first clinic admin (TSK-IAM-05-B; SEC-01, SEC-19, FR-130).

Completion criteria: a deactivated user cannot log in (401) and their active sessions are
invalidated. No API path deletes a user.
"""

from collections.abc import Iterator
from contextlib import contextmanager
import io
import threading
from typing import Any
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg
import pytest

from jude_api.domain.iam import bootstrap, users
from jude_api.domain.iam.login import hash_password
from jude_api.domain.iam.routes import AUTH_PREFIX
from jude_api.domain.iam.user_routes import USERS_PREFIX
from jude_api.main import create_app
from jude_api.platform import deps
from jude_api.platform.errors import ApiError
from jude_api.platform.iam import api_routes

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"  # noqa: S105 - test credential
NEW = {"display_name": "Aigerim T.", "login": "Tech2", "role": "technician", "password": PASSWORD}


@contextmanager
def app_conn(url: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(url) as c:
        c.execute("SET ROLE app_rw")
        c.commit()
        yield c


def add(url: str, login: str, role: str) -> uuid.UUID:
    with psycopg.connect(url) as c:
        row = c.execute(
            'INSERT INTO governance."user" (login, display_name, role, password_hash)'
            " VALUES (%s, %s, %s, %s) RETURNING id",
            (login, f"Test {login}", role, hash_password(PASSWORD)),
        ).fetchone()
        assert row is not None
        return uuid.UUID(str(row[0]))


@pytest.fixture
def url(empty_db_url: str) -> str:
    from jude_api.db.migrate import upgrade

    upgrade(empty_db_url)
    add(empty_db_url, "admin1", "clinic_admin")
    add(empty_db_url, "tech1", "technician")
    return empty_db_url


def build(url: str) -> FastAPI:
    app = create_app(db_check=lambda: None, readiness_checks={})

    def db() -> Iterator[psycopg.Connection[Any]]:
        with app_conn(url) as c:
            yield c

    app.dependency_overrides[deps.db] = db
    return app


def session(url: str, login: str) -> TestClient:
    api = TestClient(build(url), base_url="https://testserver")
    r = api.post(f"{AUTH_PREFIX}/login", json={"login": login, "password": PASSWORD})
    assert r.status_code == 200, r.text
    api.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return api


def one(url: str, sql: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...]:
    with psycopg.connect(url) as c:
        row = c.execute(sql, params).fetchone()
        assert row is not None
        return row


def scalar(url: str, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return one(url, sql, params)[0]


def events(url: str, etype: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as c:
        return c.execute(
            "SELECT e.user_id, e.role, e.object_id, s.summary_before, s.summary_after"
            " FROM audit.audit_event e LEFT JOIN audit.audit_summary s USING (seq)"
            " WHERE e.type = %s ORDER BY e.seq",
            (etype,),
        ).fetchall()


def uid(url: str, login: str) -> str:
    return str(scalar(url, 'SELECT id FROM governance."user" WHERE login = %s', (login,)))


# --- completion criteria ----------------------------------------------------------------------


def test_completion_criterion_deactivated_user_is_logged_out_and_cannot_log_in(url: str) -> None:
    admin, tech = session(url, "admin1"), session(url, "tech1")
    second = session(url, "tech1")
    tech_id = uid(url, "tech1")
    r = admin.patch(f"{USERS_PREFIX}/{tech_id}", json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False
    # the deactivation itself removes every session (not only the next request's check)
    live = "SELECT count(*) FROM governance.session WHERE user_id = %s"
    assert scalar(url, live, (tech_id,)) == 0
    for client in (tech, second):
        r = client.get(f"{USERS_PREFIX}")
        assert (r.status_code, r.json()["error"]) == (401, "SESSION_INVALID")
    r = TestClient(build(url), base_url="https://testserver").post(
        f"{AUTH_PREFIX}/login", json={"login": "tech1", "password": PASSWORD}
    )
    assert (r.status_code, r.json()["error"]) == (401, "BAD_CREDENTIALS")
    admin_id = uid(url, "admin1")
    assert events(url, "user.deactivated") == [
        (uuid.UUID(admin_id), "clinic_admin", tech_id,
         {"role": "technician", "active": True}, {"role": "technician", "active": False}),
    ]  # fmt: skip


def test_completion_criterion_no_api_path_deletes_a_user(url: str) -> None:
    user_routes = {(m, p) for m, p, _ in api_routes(build(url)) if p.startswith(USERS_PREFIX)}
    assert {m for m, _ in user_routes} == {"GET", "POST", "PATCH"}  # no DELETE anywhere
    admin = session(url, "admin1")
    r = admin.delete(f"{USERS_PREFIX}/{uid(url, 'tech1')}")
    assert (r.status_code, r.json()["error"]) == (405, "METHOD_NOT_ALLOWED")
    with app_conn(url) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute('DELETE FROM governance."user"')
    assert scalar(url, 'SELECT count(*) FROM governance."user"') == 2


# --- create -----------------------------------------------------------------------------------


def test_create_named_account_with_one_role(url: str) -> None:
    admin = session(url, "admin1")
    r = admin.post(USERS_PREFIX, json=NEW)
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {"id", "display_name", "login", "role", "active", "created_at"}
    assert (body["login"], body["display_name"], body["role"], body["active"]) == (
        "tech2", "Aigerim T.", "technician", True,
    )  # fmt: skip
    stored, created_by = one(
        url, 'SELECT password_hash, created_by FROM governance."user" WHERE id = %s', (body["id"],)
    )
    assert stored.startswith("$argon2id$") and PASSWORD not in stored
    assert str(created_by) == uid(url, "admin1")
    assert [e[2:] for e in events(url, "user.created")] == [
        (body["id"], None, {"role": "technician", "active": True})
    ]
    session(url, "TECH2 ")  # the new account can log in (login is trimmed and case-folded)
    listed = admin.get(USERS_PREFIX).json()
    assert [u["login"] for u in listed] == ["admin1", "tech1", "tech2"]
    assert all("password" not in k for u in listed for k in u)


def test_login_taken(url: str) -> None:
    admin = session(url, "admin1")
    r = admin.post(USERS_PREFIX, json={**NEW, "login": " TECH1"})
    assert (r.status_code, r.json()["error"]) == (409, "LOGIN_TAKEN")
    assert events(url, "user.created") == []


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_name_required(url: str, name: str) -> None:
    r = session(url, "admin1").post(USERS_PREFIX, json={**NEW, "display_name": name})
    assert (r.status_code, r.json()["error"]) == (422, "NAME_REQUIRED")


@pytest.mark.parametrize(
    "change",
    [
        {"login": "a b"},  # space inside
        {"login": "тех"},  # non-ASCII
        {"login": "x" * 65},
        {"password": "short"},
        {"role": "superuser"},
        {"active": False},  # unknown field on create
    ],
)
def test_invalid_create_requests(url: str, change: dict[str, Any]) -> None:
    r = session(url, "admin1").post(USERS_PREFIX, json={**NEW, **change})
    assert (r.status_code, r.json()["error"]) == (422, "REQUEST_INVALID")
    assert scalar(url, 'SELECT count(*) FROM governance."user"') == 2


# --- change -----------------------------------------------------------------------------------


def test_role_change_and_reactivation_emit_user_changed(url: str) -> None:
    admin = session(url, "admin1")
    tech_id = uid(url, "tech1")
    r = admin.patch(f"{USERS_PREFIX}/{tech_id}", json={"role": "clinic_admin"})
    assert r.status_code == 200 and r.json()["role"] == "clinic_admin"
    again = admin.patch(f"{USERS_PREFIX}/{tech_id}", json={"role": "clinic_admin"})
    assert again.status_code == 200
    admin.patch(f"{USERS_PREFIX}/{tech_id}", json={"active": False})
    admin.patch(f"{USERS_PREFIX}/{tech_id}", json={"active": True})
    changed = [(e[3], e[4]) for e in events(url, "user.changed")]
    assert changed == [
        ({"role": "technician", "active": True}, {"role": "clinic_admin", "active": True}),
        ({"role": "clinic_admin", "active": False}, {"role": "clinic_admin", "active": True}),
    ]  # the no-op PATCH wrote nothing
    assert len(events(url, "user.deactivated")) == 1


def test_role_change_takes_effect_on_the_next_request(url: str) -> None:
    admin, tech = session(url, "admin1"), session(url, "tech1")
    assert tech.get(USERS_PREFIX).status_code == 403
    admin.patch(f"{USERS_PREFIX}/{uid(url, 'tech1')}", json={"role": "clinic_admin"})
    assert tech.get(USERS_PREFIX).status_code == 200


def test_unknown_account_is_404(url: str) -> None:
    r = session(url, "admin1").patch(f"{USERS_PREFIX}/{uuid.uuid4()}", json={"active": False})
    assert (r.status_code, r.json()["error"]) == (404, "NOT_FOUND")


@pytest.mark.parametrize("change", [{"active": False}, {"role": "technician"}])
def test_last_admin(url: str, change: dict[str, Any]) -> None:
    admin = session(url, "admin1")
    admin_id = uid(url, "admin1")
    r = admin.patch(f"{USERS_PREFIX}/{admin_id}", json=change)
    assert (r.status_code, r.json()["error"]) == (409, "LAST_ADMIN")
    assert admin.get(USERS_PREFIX).status_code == 200  # nothing changed, still logged in
    assert events(url, "user.changed") == events(url, "user.deactivated") == []


def test_one_of_two_admins_may_go_but_not_both(url: str) -> None:
    add(url, "admin2", "clinic_admin")
    admin = session(url, "admin1")
    r = admin.patch(f"{USERS_PREFIX}/{uid(url, 'admin2')}", json={"active": False})
    assert r.status_code == 200
    r = admin.patch(f"{USERS_PREFIX}/{uid(url, 'admin1')}", json={"active": False})
    assert (r.status_code, r.json()["error"]) == (409, "LAST_ADMIN")


def test_concurrent_admin_removals_leave_one_admin(url: str) -> None:
    second = add(url, "admin2", "clinic_admin")
    first = uuid.UUID(uid(url, "admin1"))
    barrier, outcomes = threading.Barrier(2), []

    def remove(actor: uuid.UUID, target: uuid.UUID) -> None:
        with app_conn(url) as c:
            barrier.wait()
            try:
                with c.transaction():
                    users.update_user(
                        c, users.Actor(actor, "clinic_admin"), target, active=False,
                        now=deps.utc_now(),
                    )  # fmt: skip
                outcomes.append("ok")
            except ApiError as exc:
                outcomes.append(exc.code)

    threads = [
        threading.Thread(target=remove, args=(first, second)),
        threading.Thread(target=remove, args=(second, first)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert sorted(outcomes) == ["LAST_ADMIN", "ok"]
    active = "SELECT count(*) FROM governance.\"user\" WHERE role = 'clinic_admin' AND active"
    assert scalar(url, active) == 1


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", USERS_PREFIX, None),
        ("POST", USERS_PREFIX, NEW),
        ("PATCH", f"{USERS_PREFIX}/00000000-0000-4000-8000-000000000001", {"active": False}),
    ],
)
def test_technician_is_refused(url: str, method: str, path: str, body: Any) -> None:
    r = session(url, "tech1").request(method, path, json=body)
    assert (r.status_code, r.json()["error"]) == (403, "ROLE_FORBIDDEN")
    assert scalar(url, 'SELECT count(*) FROM governance."user"') == 2


# --- references (migration 0005) --------------------------------------------------------------


def test_every_actor_column_references_an_account(url: str) -> None:
    with psycopg.connect(url) as c:
        actor_columns = set(
            c.execute(
                """SELECT table_schema || '.' || table_name || '.' || column_name
                     FROM information_schema.columns
                    WHERE table_schema IN ('clinical', 'geometry', 'governance', 'data', 'ops')
                      AND data_type = 'uuid'
                      AND (column_name LIKE '%\\_by' OR column_name = 'user_id')"""
            ).fetchall()
        )
        referenced = set(
            c.execute(
                """SELECT n.nspname || '.' || t.relname || '.' || a.attname
                     FROM pg_constraint k
                     JOIN pg_class t ON t.oid = k.conrelid
                     JOIN pg_namespace n ON n.oid = t.relnamespace
                     JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY (k.conkey)
                    WHERE k.contype = 'f' AND k.confrelid = 'governance."user"'::regclass"""
            ).fetchall()
        )
    assert len(actor_columns) >= 24 and actor_columns <= referenced
    with psycopg.connect(url) as c, pytest.raises(psycopg.errors.ForeignKeyViolation):
        c.execute(
            """INSERT INTO clinical."case" (case_id, status, created_by)
               VALUES ('J-0000CCCC', 'active', %s)""",
            (uuid.uuid4(),),
        )


# --- first clinic admin -----------------------------------------------------------------------


def run_admin_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], url: str, password: str
) -> tuple[int, str, str]:
    monkeypatch.setenv("JUDE_DATABASE_URL", url)
    monkeypatch.setattr("sys.stdin", io.StringIO(password + "\n"))
    code = bootstrap.main(["create-first-admin", "--login", "Boss", "--display-name", "Dana K."])
    out, err = capsys.readouterr()
    return code, out.strip(), err


def test_first_admin_only_while_there_is_none(
    empty_db_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jude_api.db.migrate import upgrade

    upgrade(empty_db_url)
    code, out, _ = run_admin_cli(monkeypatch, capsys, empty_db_url, PASSWORD)
    assert code == 0
    row = one(
        empty_db_url,
        'SELECT login, role, active, created_by IS NULL FROM governance."user" WHERE id = %s',
        (out,),
    )
    assert row == ("boss", "clinic_admin", True, True)
    assert [e[:3] for e in events(empty_db_url, "user.created")] == [(None, "system", out)]
    session(empty_db_url, "boss").get(USERS_PREFIX).raise_for_status()  # and can log in

    code, _, err = run_admin_cli(monkeypatch, capsys, empty_db_url, PASSWORD)
    assert code == 1 and "active clinic admin exists" in err
    assert len(events(empty_db_url, "user.created")) == 1


def test_first_admin_password_policy_and_no_echo(
    empty_db_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jude_api.db.migrate import upgrade

    upgrade(empty_db_url)
    code, out, err = run_admin_cli(monkeypatch, capsys, empty_db_url, "short")
    assert (code, out) == (1, "") and "shorter than 12" in err
    code, out, err = run_admin_cli(monkeypatch, capsys, empty_db_url, PASSWORD)
    assert code == 0 and PASSWORD not in out + err


def test_first_admin_after_all_admins_were_deactivated_is_allowed(
    url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The API refuses to remove the last admin; this is recovery when the database says none.
    with psycopg.connect(url) as c:
        c.execute("UPDATE governance.\"user\" SET active = false WHERE role = 'clinic_admin'")
    code, _, _ = run_admin_cli(monkeypatch, capsys, url, PASSWORD)
    assert code == 0


def test_cli_usage_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JUDE_DATABASE_URL", raising=False)
    assert bootstrap.main(["create-first-admin", "--login", "x", "--display-name", "y"]) == 2
    assert bootstrap.main(["nonsense"]) == 2
