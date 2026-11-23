"""IT-FN-IAM-03: log out (TSK-IAM-03-B).

Completion criterion: a request with the old cookie after logout gets 401.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg
import pytest

from jude_api.domain.iam.login import hash_password
from jude_api.domain.iam.routes import AUTH_PREFIX
from jude_api.main import API_PREFIX, create_app
from jude_api.platform import deps

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"  # noqa: S105 - test credential
WHOAMI = f"{API_PREFIX}/_test/whoami"
LOGOUT = f"{AUTH_PREFIX}/logout"


@contextmanager
def app_conn(url: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(url) as c:
        c.execute("SET ROLE app_rw")
        c.commit()
        yield c


@pytest.fixture
def url(empty_db_url: str) -> str:
    from jude_api.db.migrate import upgrade

    upgrade(empty_db_url)
    with psycopg.connect(empty_db_url) as c:
        c.execute(
            'INSERT INTO governance."user" (login, display_name, role, password_hash)'
            " VALUES ('tech1', 'Test Technician', 'technician', %s)",
            (hash_password(PASSWORD),),
        )
    return empty_db_url


def build(url: str) -> FastAPI:
    app = create_app(db_check=lambda: None, readiness_checks={})

    @app.get(WHOAMI)
    def whoami(who: deps.CurrentRequester) -> dict[str, str]:
        return {"role": who.role}

    def db() -> Iterator[psycopg.Connection[Any]]:
        with app_conn(url) as c:
            yield c

    app.dependency_overrides[deps.db] = db
    return app


def login(api: TestClient) -> str:
    r = api.post(f"{AUTH_PREFIX}/login", json={"login": "tech1", "password": PASSWORD})
    assert r.status_code == 200
    return str(r.json()["csrf_token"])


def count(url: str, sql: str) -> int:
    with psycopg.connect(url) as c:
        row = c.execute(sql).fetchone()
        assert row is not None
        return int(row[0])


def test_completion_criterion_old_cookie_after_logout_is_401(url: str) -> None:
    api = TestClient(build(url), base_url="https://testserver")
    csrf = login(api)
    old_cookie = api.cookies["jude_session"]
    r = api.post(LOGOUT, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 204
    assert 'jude_session=""' in r.headers["set-cookie"] or "Max-Age=0" in r.headers["set-cookie"]
    replay = TestClient(build(url), base_url="https://testserver")
    replay.cookies.set("jude_session", old_cookie)
    r = replay.get(WHOAMI)
    assert (r.status_code, r.json()["error"]) == (401, "SESSION_INVALID")
    assert count(url, "SELECT count(*) FROM governance.session") == 0
    assert count(url, "SELECT count(*) FROM audit.audit_event WHERE type = 'auth.logout'") == 1


def test_logout_is_idempotent(url: str) -> None:
    api = TestClient(build(url), base_url="https://testserver")
    csrf = login(api)
    cookie = api.cookies["jude_session"]
    assert api.post(LOGOUT, headers={"X-CSRF-Token": csrf}).status_code == 204
    again = TestClient(build(url), base_url="https://testserver")
    again.cookies.set("jude_session", cookie)
    assert again.post(LOGOUT, headers={"X-CSRF-Token": csrf}).status_code == 204  # unknown -> 204
    assert TestClient(build(url), base_url="https://testserver").post(LOGOUT).status_code == 204
    assert count(url, "SELECT count(*) FROM audit.audit_event WHERE type = 'auth.logout'") == 1


def test_live_session_needs_the_csrf_token_to_log_out(url: str) -> None:
    api = TestClient(build(url), base_url="https://testserver")
    login(api)
    for headers in ({}, {"X-CSRF-Token": "wrong"}):
        r = api.post(LOGOUT, headers=headers)
        assert (r.status_code, r.json()["error"]) == (403, "CSRF_INVALID")
    assert api.get(WHOAMI).status_code == 200  # still logged in
    assert count(url, "SELECT count(*) FROM audit.audit_event WHERE type = 'auth.logout'") == 0


def test_logout_ends_only_this_session(url: str) -> None:
    first, second = (TestClient(build(url), base_url="https://testserver") for _ in range(2))
    csrf1 = login(first)
    login(second)
    assert first.post(LOGOUT, headers={"X-CSRF-Token": csrf1}).status_code == 204
    assert second.get(WHOAMI).status_code == 200
