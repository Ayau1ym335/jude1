"""IT-FN-IAM-01: login against Postgres through the real route (TSK-IAM-01-B).

Completion criteria: 5 failures within 15 min lock the account for 15 min and a 6th attempt
with the correct password returns ACCOUNT_LOCKED; the password column holds only argon2id
encodings; every attempt produces exactly one auth.* audit event (the locking attempt adds
account.locked, SEC-05).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
from typing import Any
import uuid

from fastapi.testclient import TestClient
import psycopg
import pytest

from jude_api.domain.iam import routes
from jude_api.domain.iam.login import hash_password
from jude_api.main import create_app
from jude_api.platform import deps
from jude_api.platform.security_config import SecurityConfig, security_config

pytestmark = pytest.mark.integration

LOGIN_URL = f"{routes.AUTH_PREFIX}/login"
PASSWORD = "correct horse battery staple"  # noqa: S105 - test credential
T0 = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)


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
    return empty_db_url


def add_user(
    url: str, login: str = "tech1", role: str = "technician", active: bool = True
) -> uuid.UUID:
    with psycopg.connect(url) as c:
        row = c.execute(
            'INSERT INTO governance."user" (login, display_name, role, password_hash, active)'
            " VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (login, "Test Technician", role, hash_password(PASSWORD), active),
        ).fetchone()
        assert row is not None
        return row[0]  # type: ignore[no-any-return]


def client(url: str, clock: Clock, cfg: SecurityConfig | None = None) -> TestClient:
    app = create_app(db_check=lambda: None, readiness_checks={})

    def db() -> Iterator[psycopg.Connection[Any]]:
        with app_conn(url) as c:
            yield c

    app.dependency_overrides[deps.db] = db
    app.dependency_overrides[deps.clock] = lambda: clock
    if cfg is not None:
        app.dependency_overrides[security_config] = lambda: cfg
    return TestClient(app)


def audit(url: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as c:
        return c.execute(
            "SELECT e.type, e.user_id, e.ui_session_id, s.summary_after FROM audit.audit_event e"
            " LEFT JOIN audit.audit_summary s USING (seq) ORDER BY e.seq"
        ).fetchall()


def without_cid(resp: Any) -> dict[str, Any]:
    return {k: v for k, v in resp.json().items() if k != "correlation_id"}


def attempt(api: TestClient, password: str, login: str = "tech1") -> Any:
    return api.post(LOGIN_URL, json={"login": login, "password": password})


def test_success_sets_secure_cookie_and_stores_only_token_hashes(url: str) -> None:
    uid = add_user(url)
    resp = attempt(client(url, Clock()), PASSWORD, login="  TECH1 ")  # trimmed, case-folded
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"] == {"id": str(uid), "display_name": "Test Technician", "role": "technician"}
    cookie = resp.headers["set-cookie"]
    assert all(
        flag in cookie
        for flag in ("jude_session=", "HttpOnly", "Secure", "SameSite=strict", "Path=/")
    )
    token = resp.cookies["jude_session"]
    with psycopg.connect(url) as c:
        sid, csrf_hash, ui = c.execute(
            "SELECT id, csrf_hash, ui_session_id FROM governance.session"
        ).fetchone()  # type: ignore[misc]
        dumped = str(c.execute("SELECT * FROM governance.session").fetchall())
    assert sid == hashlib.sha256(token.encode()).hexdigest()
    assert csrf_hash == hashlib.sha256(body["csrf_token"].encode()).hexdigest()
    assert token not in dumped and body["csrf_token"] not in dumped
    assert audit(url) == [("auth.login", uid, ui, None)]


def test_completion_criterion_lockout_after_five_failures(url: str) -> None:
    uid = add_user(url)
    clock = Clock()
    api = client(url, clock)
    for i in range(5):
        clock.now = T0 + timedelta(minutes=2 * i)  # all inside the 15-minute window
        r = attempt(api, "wrong")
        assert (r.status_code, r.json()["error"]) == (401, "BAD_CREDENTIALS")
    locked_at = clock.now
    clock.now += timedelta(seconds=30)
    sixth = attempt(api, PASSWORD)
    assert (sixth.status_code, sixth.json()["error"]) == (423, "ACCOUNT_LOCKED")
    assert sixth.json()["gates"][0]["detail"] == (locked_at + timedelta(minutes=15)).isoformat()
    clock.now = locked_at + timedelta(minutes=15, seconds=1)  # lock expired
    assert attempt(api, PASSWORD).status_code == 200
    types = [t for t, *_ in audit(url)]
    assert types == ["auth.login_failed"] * 4 + ["account.locked", "auth.login_failed"] + [
        "auth.login_failed",  # the 6th attempt, refused while locked
        "auth.login",
    ]
    reasons = [s["reason"] for t, _, _, s in audit(url) if t == "auth.login_failed"]
    assert reasons == ["bad_password"] * 5 + ["locked"]
    with psycopg.connect(url) as c:
        assert c.execute("SELECT count(*) FROM governance.login_failure").fetchone() == (0,)
        assert c.execute(
            'SELECT locked_until FROM governance."user" WHERE id = %s', (uid,)
        ).fetchone() == (locked_at + timedelta(minutes=15),)


def test_failures_outside_the_window_do_not_lock(url: str) -> None:
    add_user(url)
    clock = Clock()
    api = client(url, clock)
    for _ in range(4):
        attempt(api, "wrong")
    clock.now = T0 + timedelta(minutes=16)  # the first four fell out of the window
    assert attempt(api, "wrong").status_code == 401
    assert attempt(api, PASSWORD).status_code == 200


def test_unknown_login_answers_like_a_wrong_password_and_stores_no_login(url: str) -> None:
    add_user(url)
    api = client(url, Clock())
    unknown = attempt(api, PASSWORD, login="Aigerim.Ivanova")
    wrong = attempt(api, "wrong")
    assert unknown.status_code == wrong.status_code == 401
    assert without_cid(unknown) == without_cid(wrong)
    rows = audit(url)
    assert rows[0][:2] == ("auth.login_failed", None) and rows[0][3] == {"reason": "unknown_login"}
    with psycopg.connect(url) as c:
        dump = str(c.execute("SELECT * FROM audit.audit_event").fetchall())
        dump += str(c.execute("SELECT * FROM audit.audit_summary").fetchall())
    assert "aigerim" not in dump.lower()


def test_deactivated_account_cannot_log_in(url: str) -> None:
    add_user(url, active=False)
    r = attempt(client(url, Clock()), PASSWORD)
    assert (r.status_code, r.json()["error"]) == (401, "BAD_CREDENTIALS")
    assert audit(url)[0][3] == {"reason": "deactivated"}


def test_exactly_one_auth_event_per_attempt(url: str) -> None:
    add_user(url)
    api = client(url, Clock())
    outcomes = [attempt(api, p).status_code for p in ("wrong", PASSWORD, "wrong", PASSWORD)]
    assert outcomes == [401, 200, 401, 200]
    assert [t for t, *_ in audit(url)] == ["auth.login_failed", "auth.login"] * 2


def test_completion_criterion_password_column_holds_only_argon2id(url: str) -> None:
    add_user(url)
    add_user(url, login="admin1", role="clinic_admin")
    with psycopg.connect(url) as c:
        assert c.execute(
            "SELECT bool_and(password_hash LIKE '$argon2id$v=19$%') FROM governance.\"user\""
        ).fetchone() == (True,)
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(
                'INSERT INTO governance."user" (login, display_name, role, password_hash)'
                " VALUES ('plain', 'P', 'technician', 'secret')"
            )


def test_lockout_values_come_from_security_config(url: str) -> None:
    add_user(url)
    clock = Clock()
    cfg = SecurityConfig(
        max_failures=2,
        window_seconds=60,
        lock_seconds=30,
        idle_timeout_seconds=1800,
        last_seen_write_interval_seconds=60,
    )
    api = client(url, clock, cfg)
    attempt(api, "wrong")
    attempt(api, "wrong")
    assert attempt(api, PASSWORD).status_code == 423
    clock.now = T0 + timedelta(seconds=31)
    assert attempt(api, PASSWORD).status_code == 200
    assert security_config().max_failures == 5  # the shipped SD-01 value
