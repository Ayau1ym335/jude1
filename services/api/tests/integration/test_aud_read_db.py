"""IT-FN-AUD-02: log read access (TSK-AUD-02-A; SEC-15, FR-164).

Completion criterion: a scripted session reading each object type yields one read event per
access, with user, role, UTC time, case id and object id. The real download endpoints arrive
with their tasks (FN-SCN-12, FN-EXP-03, FN-RPT-03, FN-AUD-05, FN-CAS-07). Here test routes call
the same ``logged_download`` those endpoints will use, over real sessions, the real audit chain
and a real database.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
import psycopg
import pytest

from jude_api.domain.iam.login import hash_password
from jude_api.domain.iam.routes import AUTH_PREFIX
from jude_api.main import API_PREFIX, create_app
from jude_api.platform import aud, aud_read, deps
from jude_api.platform.aud_read import READ_EVENTS, ReadKind, logged_download

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"  # noqa: S105 - test credential
CASE = "J-0123ABCD"
READ = f"{API_PREFIX}/_test/read"
BODY = b"synthetic object bytes"


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
        for login, role in (("tech1", "technician"), ("admin1", "clinic_admin")):
            c.execute(
                'INSERT INTO governance."user" (login, display_name, role, password_hash)'
                " VALUES (%s, %s, %s, %s)",
                (login, f"Test {login}", role, hash_password(PASSWORD)),
            )
    return empty_db_url


def build(url: str) -> FastAPI:
    app = create_app(db_check=lambda: None, readiness_checks={})

    @app.get(READ + "/{kind}/{object_id}")
    def read(kind: ReadKind, object_id: str, who: deps.CurrentRequester, conn: deps.Db) -> Response:
        conn.execute("SELECT 1").fetchone()  # the request's own read: an open transaction
        case_id = None if kind is ReadKind.AUDIT_CSV else CASE
        return logged_download(conn, who, kind, case_id=case_id, object_id=object_id,
                               content=BODY, media_type="application/octet-stream",
                               filename=f"{object_id}.bin")  # fmt: skip

    def db() -> Iterator[psycopg.Connection[Any]]:
        with app_conn(url) as c:
            yield c

    app.dependency_overrides[deps.db] = db
    return app


def session(url: str, login: str) -> TestClient:
    api = TestClient(build(url), base_url="https://testserver")
    r = api.post(f"{AUTH_PREFIX}/login", json={"login": login, "password": PASSWORD})
    assert r.status_code == 200
    return api


def read_events(url: str) -> list[tuple[Any, ...]]:
    types = tuple({e.event_type for e in READ_EVENTS.values()})
    with psycopg.connect(url) as c:
        return c.execute(
            "SELECT e.type, e.user_id, e.role, e.at_utc, e.case_id, e.object_type, e.object_id"
            " FROM audit.audit_event e WHERE e.type = ANY(%s) ORDER BY e.seq",
            (list(types),),
        ).fetchall()


def user_id(url: str, login: str) -> Any:
    with psycopg.connect(url) as c:
        row = c.execute('SELECT id FROM governance."user" WHERE login = %s', (login,)).fetchone()
        assert row is not None
        return row[0]


# --- completion criterion ------------------------------------------------------------------------


def test_completion_criterion_one_read_event_per_access_with_all_fields(url: str) -> None:
    api = session(url, "tech1")
    started = datetime.now(UTC) - timedelta(seconds=5)
    script = [(kind, f"obj-{kind.value}") for kind in ReadKind] + [(ReadKind.EXPORT, "obj-export")]
    for kind, object_id in script:
        r = api.get(f"{READ}/{kind.value}/{object_id}")
        assert r.status_code == 200 and r.content == BODY
        assert r.headers["cache-control"] == "no-store"
    events = read_events(url)
    assert len(events) == len(script)  # one per access, a repeated read counts again
    tech = user_id(url, "tech1")
    for (kind, object_id), event in zip(script, events, strict=True):
        etype, uid, role, at, case_id, otype, oid = event
        spec = READ_EVENTS[kind]
        assert (etype, otype, oid) == (spec.event_type, spec.object_type, object_id)
        assert (uid, role) == (tech, "technician")
        assert case_id == (None if kind is ReadKind.AUDIT_CSV else CASE)
        assert at.utcoffset() is not None and started <= at <= datetime.now(UTC)


def test_read_events_join_the_hash_chain_and_name_the_ui_session(url: str) -> None:
    api = session(url, "admin1")
    api.get(f"{READ}/report/r-1")
    with psycopg.connect(url) as c:
        row = c.execute(
            "SELECT e.role, e.ui_session_id, s.ui_session_id FROM audit.audit_event e,"
            " governance.session s WHERE e.type = 'report.downloaded'"
        ).fetchone()
    assert row is not None and row[0] == "clinic_admin" and row[1] == row[2]
    with psycopg.connect(url) as c:
        check = aud.verify(c)
        assert check.first_broken_seq is None and check.checked >= 2


# --- no unlogged read --------------------------------------------------------------------------


def test_audit_failure_refuses_the_download(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    api = session(url, "tech1")

    def broken(*_: Any, **__: Any) -> int:
        raise psycopg.OperationalError("audit store unreachable")

    monkeypatch.setattr(aud, "append", broken)  # the module aud_read appends through
    r = api.get(f"{READ}/scan_blob/obj-1")
    assert (r.status_code, r.json()["error"]) == (503, "AUDIT_UNAVAILABLE")
    assert BODY not in r.content
    assert read_events(url) == []


def test_unauthenticated_read_is_refused_before_any_event(url: str) -> None:
    anon = TestClient(build(url), base_url="https://testserver")
    r = anon.get(f"{READ}/prescription/p-1")
    assert (r.status_code, r.json()["error"]) == (401, "SESSION_INVALID")
    assert read_events(url) == []


def test_event_is_committed_before_the_body_is_built(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[int] = []
    real: Callable[..., Response] = Response

    def spy(*args: Any, **kwargs: Any) -> Response:
        seen.append(len(read_events(url)))  # another connection: only committed rows count
        return real(*args, **kwargs)

    monkeypatch.setattr(aud_read, "Response", spy)
    session(url, "tech1").get(f"{READ}/display_mesh/m-1")
    assert seen == [1]
