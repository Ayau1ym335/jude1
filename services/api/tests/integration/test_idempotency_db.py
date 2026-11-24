"""IT-FN-API-01: idempotent, concurrency-safe mutations (TSK-API-01-A; NFR-07).

Completion criteria:
- kill the client after the commit; on reopen the operation is there, in 50/50 trials;
- a replay with the same key returns an identical body and creates no second audit event.

Exercised through POST /api/v1/users, the first route that mutates under a session.
"""

from collections.abc import Iterator
from contextlib import contextmanager
import http.client
import json
import socket
import threading
import time
from typing import Any
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg
import pytest
import uvicorn

from jude_api.domain.iam.login import hash_password
from jude_api.domain.iam.routes import AUTH_PREFIX
from jude_api.domain.iam.user_routes import USERS_PREFIX
from jude_api.main import create_app
from jude_api.platform import deps

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"  # noqa: S105 - test credential
TRIALS = 50


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
        for login in ("admin1", "admin2"):
            c.execute(
                'INSERT INTO governance."user" (login, display_name, role, password_hash)'
                " VALUES (%s, %s, 'clinic_admin', %s)",
                (login, f"Test {login}", hash_password(PASSWORD)),
            )
    return empty_db_url


def build(url: str) -> FastAPI:
    app = create_app(db_check=lambda: None, readiness_checks={})

    def db() -> Iterator[psycopg.Connection[Any]]:
        with app_conn(url) as c:
            yield c

    app.dependency_overrides[deps.db] = db
    return app


def session(url: str, login: str = "admin1") -> TestClient:
    api = TestClient(build(url), base_url="https://testserver")
    r = api.post(f"{AUTH_PREFIX}/login", json={"login": login, "password": PASSWORD})
    assert r.status_code == 200, r.text
    api.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return api


def new_user(login: str) -> dict[str, str]:
    return {"display_name": f"Name {login}", "login": login, "role": "technician",
            "password": PASSWORD}  # fmt: skip


def count(url: str, sql: str, params: tuple[Any, ...] = ()) -> int:
    with psycopg.connect(url) as c:
        row = c.execute(sql, params).fetchone()
        assert row is not None
        return int(row[0])


def created(url: str) -> int:
    return count(url, "SELECT count(*) FROM audit.audit_event WHERE type = 'user.created'")


def accounts(url: str) -> int:
    return count(url, 'SELECT count(*) FROM governance."user"')


# --- completion criteria ----------------------------------------------------------------------


def test_completion_criterion_replay_returns_identical_body_and_no_second_event(url: str) -> None:
    api, key = session(url), str(uuid.uuid4())
    first = api.post(USERS_PREFIX, json=new_user("tech1"), headers={"Idempotency-Key": key})
    assert first.status_code == 201 and "idempotent-replayed" not in first.headers
    for _ in range(3):
        again = api.post(USERS_PREFIX, json=new_user("tech1"), headers={"Idempotency-Key": key})
        assert (again.status_code, again.content) == (201, first.content)  # byte-identical
        assert again.headers["idempotent-replayed"] == "true"
    assert (accounts(url), created(url)) == (3, 1)
    assert count(url, "SELECT count(*) FROM ops.idempotency_key") == 1


class Server:
    """The app on a real socket, so a client can drop its connection mid-request."""

    def __init__(self, app: FastAPI) -> None:
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> "Server":
        self.thread.start()
        deadline = time.monotonic() + 20
        while not self.server.started:
            assert time.monotonic() < deadline, "server did not start"
            time.sleep(0.02)
        self.port = self.server.servers[0].sockets[0].getsockname()[1]
        return self

    def __exit__(self, *_: object) -> None:
        self.server.should_exit = True
        self.thread.join(20)

    def request(
        self, method: str, path: str, body: Any, headers: dict[str, str]
    ) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            payload = json.dumps(body).encode() if body is not None else None
            conn.request(method, path, body=payload,
                         headers={"Content-Type": "application/json", **headers})  # fmt: skip
            r = conn.getresponse()
            return r.status, r.read()
        finally:
            conn.close()

    def send_and_vanish(self, path: str, body: Any, headers: dict[str, str]) -> None:
        """Send a complete request, then close the socket without reading the response."""
        payload = json.dumps(body).encode()
        head = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        raw = (
            f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n{head}Connection: close\r\n\r\n"
        ).encode()
        with socket.create_connection(("127.0.0.1", self.port), timeout=20) as s:
            s.sendall(raw + payload)


def test_completion_criterion_client_killed_after_commit_finds_the_operation(url: str) -> None:
    with Server(build(url)) as srv:
        # The cookie is Secure (https only); the plain-http test socket sends it by hand.
        conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=20)
        conn.request("POST", f"{AUTH_PREFIX}/login",
                     body=json.dumps({"login": "admin1", "password": PASSWORD}),
                     headers={"Content-Type": "application/json"})  # fmt: skip
        r = conn.getresponse()
        csrf = json.loads(r.read())["csrf_token"]
        cookie = r.getheader("set-cookie", "").split(";")[0]
        conn.close()
        auth = {"Cookie": cookie, "X-CSRF-Token": csrf}

        persisted = 0
        for i in range(TRIALS):
            key, login = str(uuid.uuid4()), f"trial{i:02d}"
            srv.send_and_vanish(USERS_PREFIX, new_user(login), {**auth, "Idempotency-Key": key})
            # "reopen": the operation is there once the server has committed it
            deadline = time.monotonic() + 15
            q = 'SELECT count(*) FROM governance."user" WHERE login = %s'
            while count(url, q, (login,)) == 0 and time.monotonic() < deadline:
                time.sleep(0.02)
            status, listed = srv.request("GET", USERS_PREFIX, None, auth)
            assert status == 200
            persisted += login in {u["login"] for u in json.loads(listed)}
            # the client's retry after reconnecting gets the original response, no duplicate
            status, replay = srv.request(
                "POST", USERS_PREFIX, new_user(login), {**auth, "Idempotency-Key": key}
            )
            assert status == 201 and json.loads(replay)["login"] == login
    assert persisted == TRIALS  # 50/50
    assert (accounts(url), created(url)) == (2 + TRIALS, TRIALS)


# --- refusals ---------------------------------------------------------------------------------


def test_missing_key_is_428_after_the_session_check(url: str) -> None:
    api = session(url)
    r = api.post(USERS_PREFIX, json=new_user("tech1"))
    assert (r.status_code, r.json()["error"]) == (428, "IDEMPOTENCY_KEY_REQUIRED")
    anonymous = TestClient(build(url), base_url="https://testserver")
    r = anonymous.post(USERS_PREFIX, json=new_user("tech1"))
    assert (r.status_code, r.json()["error"]) == (401, "SESSION_INVALID")
    r = session(url).post(USERS_PREFIX, json=new_user("tech1"), headers={"X-CSRF-Token": "x"})
    assert (r.status_code, r.json()["error"]) == (403, "CSRF_INVALID")
    assert accounts(url) == 2


@pytest.mark.parametrize(
    "key",
    ["not-a-uuid", "", str(uuid.uuid1()), "{" + str(uuid.uuid4()) + "}", str(uuid.uuid4())[:-1]],
)
def test_malformed_key_is_refused(url: str, key: str) -> None:
    r = session(url).post(USERS_PREFIX, json=new_user("tech1"), headers={"Idempotency-Key": key})
    assert (r.status_code, r.json()["error"]) == (422, "REQUEST_INVALID")
    assert r.json()["gates"][0]["detail"] == "header.Idempotency-Key"


def test_key_text_is_case_insensitive(url: str) -> None:
    api, key = session(url), str(uuid.uuid4())
    first = api.post(USERS_PREFIX, json=new_user("tech1"), headers={"Idempotency-Key": key})
    upper = api.post(USERS_PREFIX, json=new_user("tech1"), headers={"Idempotency-Key": key.upper()})
    assert upper.content == first.content and upper.headers["idempotent-replayed"] == "true"


def test_same_key_for_a_different_request_is_refused(url: str) -> None:
    api, key = session(url), str(uuid.uuid4())
    assert api.post(USERS_PREFIX, json=new_user("tech1"),
                    headers={"Idempotency-Key": key}).status_code == 201  # fmt: skip
    r = api.post(USERS_PREFIX, json=new_user("tech2"), headers={"Idempotency-Key": key})
    assert (r.status_code, r.json()["error"]) == (422, "IDEMPOTENCY_KEY_REUSED")
    # the same key on another path is another request, too
    r = api.patch(f"{USERS_PREFIX}/{uuid.uuid4()}", json={"active": False},
                  headers={"Idempotency-Key": key})  # fmt: skip
    assert (r.status_code, r.json()["error"]) == (422, "IDEMPOTENCY_KEY_REUSED")
    assert (accounts(url), created(url)) == (3, 1)


def test_keys_are_scoped_to_the_user(url: str) -> None:
    key = str(uuid.uuid4())
    one = session(url, "admin1").post(USERS_PREFIX, json=new_user("tech1"),
                                      headers={"Idempotency-Key": key})  # fmt: skip
    two = session(url, "admin2").post(USERS_PREFIX, json=new_user("tech2"),
                                      headers={"Idempotency-Key": key})  # fmt: skip
    assert (one.status_code, two.status_code) == (201, 201)
    assert "idempotent-replayed" not in two.headers and created(url) == 2


def test_a_refusal_is_not_stored_so_a_corrected_retry_runs(url: str) -> None:
    api, key = session(url), str(uuid.uuid4())
    taken = new_user("admin1")  # LOGIN_TAKEN: the transaction rolls back
    for _ in range(2):  # the same refused request is refused again (not replayed)
        r = api.post(USERS_PREFIX, json=taken, headers={"Idempotency-Key": key})
        assert (r.status_code, r.json()["error"]) == (409, "LOGIN_TAKEN")
        assert "idempotent-replayed" not in r.headers
    assert count(url, "SELECT count(*) FROM ops.idempotency_key") == 0
    with psycopg.connect(url) as c:  # the cause goes away: the login is free now
        c.execute("UPDATE governance.\"user\" SET login = 'boss' WHERE login = 'admin1'")
    r = api.post(USERS_PREFIX, json=taken, headers={"Idempotency-Key": key})
    assert r.status_code == 201 and created(url) == 1


def test_concurrent_requests_with_one_key_run_once(url: str) -> None:
    api, key = session(url), str(uuid.uuid4())
    barrier, results = threading.Barrier(4), []

    def post() -> None:
        client = TestClient(api.app, base_url="https://testserver", cookies=api.cookies)
        barrier.wait()
        results.append(client.post(USERS_PREFIX, json=new_user("tech1"),
                                   headers={**api.headers, "Idempotency-Key": key}))  # fmt: skip

    threads = [threading.Thread(target=post) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert [r.status_code for r in results] == [201] * 4
    assert len({r.content for r in results}) == 1
    assert sum(r.headers.get("idempotent-replayed") == "true" for r in results) == 3
    assert (accounts(url), created(url)) == (3, 1)


def test_patch_replay_does_not_repeat_the_change(url: str) -> None:
    api = session(url)
    tech = api.post(USERS_PREFIX, json=new_user("tech1"),
                    headers={"Idempotency-Key": str(uuid.uuid4())}).json()  # fmt: skip
    key = str(uuid.uuid4())
    path = f"{USERS_PREFIX}/{tech['id']}"
    first = api.patch(path, json={"active": False}, headers={"Idempotency-Key": key})
    # someone reactivates in between; the retry of the first PATCH must not deactivate again
    api.patch(path, json={"active": True}, headers={"Idempotency-Key": str(uuid.uuid4())})
    again = api.patch(path, json={"active": False}, headers={"Idempotency-Key": key})
    assert again.content == first.content and again.headers["idempotent-replayed"] == "true"
    deactivated = "SELECT count(*) FROM audit.audit_event WHERE type = 'user.deactivated'"
    assert count(url, deactivated) == 1
    assert count(url, 'SELECT count(*) FROM governance."user" WHERE active') == 3


def test_database_checks_the_stored_body_hash(url: str) -> None:
    with app_conn(url) as c, pytest.raises(psycopg.errors.CheckViolation):
        c.execute(
            """INSERT INTO ops.idempotency_key
                   (user_id, key, request_sha, status_code, body_sha, body, body_bytes)
               SELECT id, 'k', repeat('0', 64), 201, repeat('0', 64), '{}', '\\x7b7d'::bytea
                 FROM governance."user" LIMIT 1"""
        )
