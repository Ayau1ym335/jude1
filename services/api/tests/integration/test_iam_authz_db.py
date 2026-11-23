"""IT-FN-IAM-04 / VER-12: generated role x action matrix over real sessions (TSK-IAM-04-A).

Completion criteria: the generated role x action matrix test passes for 100 % of cells; clinic
admin approve/export calls return 403. Each denied cell also writes one authz.denied event.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import psycopg
import pytest

from jude_api.domain.iam.login import hash_password
from jude_api.domain.iam.routes import AUTH_PREFIX
from jude_api.main import API_PREFIX, create_app
from jude_api.platform import deps
from jude_api.platform.authz import ActionCheck, ensure_case_writable, matrix
from jude_api.platform.deps import Requester
from jude_api.platform.errors import ApiError

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"  # noqa: S105 - test credential
USERS = {"technician": "tech1", "clinic_admin": "admin1"}


@contextmanager
def app_conn(url: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(url) as c:
        c.execute("SET ROLE app_rw")
        c.commit()
        yield c


@pytest.fixture(scope="module")
def url(migrated_url: str) -> str:
    with psycopg.connect(migrated_url) as c:
        for role, login in USERS.items():
            c.execute(
                'INSERT INTO governance."user" (login, display_name, role, password_hash)'
                " VALUES (%s, %s, %s, %s) ON CONFLICT (login) DO NOTHING",
                (login, f"Test {role}", role, hash_password(PASSWORD)),
            )
    return migrated_url


def probe_path(action: str) -> str:
    return f"{API_PREFIX}/_test/action/{action}"


def build(url: str) -> FastAPI:
    app = create_app(db_check=lambda: None, readiness_checks={})
    for action in matrix().allow:  # one generated probe route per action key

        def probe(who: Annotated[Requester, Depends(ActionCheck(action))]) -> dict[str, str]:
            return {"role": who.role}

        app.add_api_route(probe_path(action), probe, methods=["GET"], name=f"probe_{action}")

    def db() -> Iterator[psycopg.Connection[Any]]:
        with app_conn(url) as c:
            yield c

    app.dependency_overrides[deps.db] = db
    return app


def session(app: FastAPI, role: str) -> TestClient:
    api = TestClient(app, base_url="https://testserver")
    r = api.post(f"{AUTH_PREFIX}/login", json={"login": USERS[role], "password": PASSWORD})
    assert r.status_code == 200
    return api


def denied_events(url: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as c:
        return c.execute(
            "SELECT role, object_id FROM audit.audit_event WHERE type = 'authz.denied' ORDER BY seq"
        ).fetchall()


def test_completion_criterion_generated_matrix_100_percent_of_cells(url: str) -> None:
    app = build(url)
    m = matrix()
    before = len(denied_events(url))
    cells = mismatches = 0
    expected_denials: list[tuple[str, str]] = []
    for role in m.roles:
        api = session(app, role)
        for action in sorted(m.allow):
            r = api.get(probe_path(action))
            want = 200 if m.allowed(role, action) else 403
            cells += 1
            if r.status_code != want or (want == 403 and r.json()["error"] != "ROLE_FORBIDDEN"):
                mismatches += 1
            if want == 403:
                expected_denials.append((role, action))
    assert cells == len(m.roles) * len(m.allow) and mismatches == 0
    assert denied_events(url)[before:] == expected_denials  # one authz.denied per denial


def test_completion_criterion_clinic_admin_approve_and_export_are_forbidden(url: str) -> None:
    api = session(build(url), "clinic_admin")
    for action in ("FN-REV-04", "FN-EXP-01", "FN-EXP-03"):
        r = api.get(probe_path(action))
        assert (r.status_code, r.json()["error"]) == (403, "ROLE_FORBIDDEN"), action


def test_unauthenticated_probe_is_401_not_403(url: str) -> None:
    r = TestClient(build(url), base_url="https://testserver").get(probe_path("FN-CAS-02"))
    assert (r.status_code, r.json()["error"]) == (401, "SESSION_INVALID")


def test_archived_case_is_read_only(url: str) -> None:
    with psycopg.connect(url) as c:
        account = c.execute('SELECT min(id::text)::uuid FROM governance."user"').fetchone()
        assert account is not None
        c.execute(
            'INSERT INTO clinical."case" (case_id, status, archived_by, archived_at, created_by)'
            " VALUES ('J-0000AAAA', 'active', NULL, NULL, %(u)s),"
            " ('J-0000BBBB', 'archived', %(u)s, now(), %(u)s) ON CONFLICT DO NOTHING",
            {"u": account[0]},
        )
    with app_conn(url) as c:
        ensure_case_writable(c, "J-0000AAAA")
        with pytest.raises(ApiError) as archived:
            ensure_case_writable(c, "J-0000BBBB")
        assert archived.value.code == "CASE_ARCHIVED"
        with pytest.raises(ApiError) as missing:
            ensure_case_writable(c, "J-0000ZZZZ")
        assert missing.value.code == "NOT_FOUND"
