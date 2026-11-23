"""IT-FN-IAM-02: session validation, idle timeout and CSRF (TSK-IAM-02-A).

Completion criteria: a request after 31 min of inactivity gets 401; a mutating request
without or with a wrong CSRF token gets 403 on 100 % of the mutating endpoints of the app.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg
import pytest

from jude_api.domain.iam.login import hash_password
from jude_api.domain.iam.routes import AUTH_PREFIX
from jude_api.main import API_PREFIX, create_app
from jude_api.platform import deps
from jude_api.platform.iam import SESSIONLESS, mutating_routes

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"  # noqa: S105 - test credential
T0 = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
WHOAMI = f"{API_PREFIX}/_test/whoami"
MUTATE = f"{API_PREFIX}/_test/mutate"


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


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


def build(url: str, clock: Clock) -> FastAPI:
    app = create_app(db_check=lambda: None, readiness_checks={})

    @app.get(WHOAMI)
    def whoami(who: deps.CurrentRequester) -> dict[str, str]:
        return {"user_id": str(who.user_id), "role": who.role}

    @app.post(MUTATE)
    def mutate(who: deps.CurrentRequester) -> dict[str, str]:
        return {"ok": "yes"}

    def db() -> Iterator[psycopg.Connection[Any]]:
        with app_conn(url) as c:
            yield c

    app.dependency_overrides[deps.db] = db
    app.dependency_overrides[deps.clock] = lambda: clock
    return app


def login(api: TestClient) -> str:
    r = api.post(f"{AUTH_PREFIX}/login", json={"login": "tech1", "password": PASSWORD})
    assert r.status_code == 200
    return str(r.json()["csrf_token"])


def sessions(url: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as c:
        return c.execute("SELECT id, last_seen_at FROM governance.session").fetchall()


def test_completion_criterion_idle_31_minutes_gives_401(url: str) -> None:
    clock = Clock()
    api = TestClient(build(url, clock), base_url="https://testserver")
    login(api)
    clock.now = T0 + timedelta(minutes=29)
    assert api.get(WHOAMI).status_code == 200  # activity refreshes last_seen_at
    clock.now = T0 + timedelta(minutes=29 + 31)
    r = api.get(WHOAMI)
    assert (r.status_code, r.json()["error"]) == (401, "SESSION_EXPIRED")
    assert sessions(url) == []  # the expired session is deleted
    r = api.get(WHOAMI)
    assert (r.status_code, r.json()["error"]) == (401, "SESSION_INVALID")


def test_exactly_at_the_limit_is_still_valid(url: str) -> None:
    clock = Clock()
    api = TestClient(build(url, clock), base_url="https://testserver")
    login(api)
    clock.now = T0 + timedelta(minutes=30)
    assert api.get(WHOAMI).status_code == 200  # expired only when idle > 30 min


def test_completion_criterion_csrf_on_every_mutating_endpoint(url: str) -> None:
    clock = Clock()
    app = build(url, clock)
    api = TestClient(app, base_url="https://testserver")
    csrf = login(api)
    checked = 0
    for method, path, _route in mutating_routes(app):
        if (method, path) in SESSIONLESS:
            continue
        target = path.replace("{job_id}", str(uuid.uuid4()))
        for headers in ({}, {"X-CSRF-Token": "wrong"}, {"X-CSRF-Token": csrf + "x"}):
            r = api.request(method, target, headers=headers)
            assert (r.status_code, r.json()["error"]) == (403, "CSRF_INVALID"), (method, path)
        checked += 1
    assert checked >= 1
    assert api.post(MUTATE, headers={"X-CSRF-Token": csrf}).json() == {"ok": "yes"}
    assert api.get(WHOAMI).status_code == 200  # reads need no CSRF token


def test_unknown_or_tampered_cookie_is_invalid(url: str) -> None:
    api = TestClient(build(url, Clock()), base_url="https://testserver")
    login(api)
    api.cookies.clear()
    api.cookies.set("jude_session", "forged-token")
    r = api.get(WHOAMI)
    assert (r.status_code, r.json()["error"]) == (401, "SESSION_INVALID")


def test_deactivated_user_loses_the_session(url: str) -> None:
    api = TestClient(build(url, Clock()), base_url="https://testserver")
    login(api)
    with psycopg.connect(url) as c:
        c.execute('UPDATE governance."user" SET active = false')
    r = api.get(WHOAMI)
    assert (r.status_code, r.json()["error"]) == (401, "SESSION_INVALID")
    assert sessions(url) == []


def test_last_seen_is_written_at_most_once_a_minute(url: str) -> None:
    clock = Clock()
    api = TestClient(build(url, clock), base_url="https://testserver")
    login(api)
    clock.now = T0 + timedelta(seconds=30)
    api.get(WHOAMI)
    assert sessions(url)[0][1] == T0  # not yet: within 60 s
    clock.now = T0 + timedelta(seconds=61)
    api.get(WHOAMI)
    assert sessions(url)[0][1] == T0 + timedelta(seconds=61)


def test_session_context_reaches_the_route(url: str) -> None:
    api = TestClient(build(url, Clock()), base_url="https://testserver")
    login(api)
    assert api.get(WHOAMI).json()["role"] == "technician"
