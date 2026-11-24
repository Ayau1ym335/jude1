"""UT-FN-API-01: idempotency start-up check, request fingerprint, If-Match (no database)."""

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
import pytest

from jude_api.main import API_PREFIX, create_app
from jude_api.platform import deps
from jude_api.platform.errors import ApiError, install_error_handlers
from jude_api.platform.idempotency import (
    IdempotentRequest,
    IfMatch,
    assert_mutations_are_idempotent,
    ensure_version,
    etag,
    request_sha,
)


def test_app_starts_with_every_session_mutation_idempotent() -> None:
    assert_mutations_are_idempotent(create_app(db_check=lambda: None, readiness_checks={}))


def test_session_mutation_without_idempotency_refuses_to_start() -> None:
    router = APIRouter(prefix=f"{API_PREFIX}/_test")

    @router.post("/plain")
    def plain(who: deps.CurrentRequester) -> None:
        return None

    @router.post("/keyed")
    def keyed(idem: IdempotentRequest) -> None:
        return None

    app = FastAPI()
    app.include_router(router)
    with pytest.raises(RuntimeError, match=r"POST /api/v1/_test/plain$"):
        assert_mutations_are_idempotent(app)


def test_login_and_logout_need_no_key() -> None:
    # sessionless routes: no user to scope a key to (login), idempotent by design (logout)
    app = FastAPI()
    router = APIRouter(prefix=f"{API_PREFIX}/auth")

    @router.post("/login")
    def login() -> None:
        return None

    app.include_router(router)
    assert_mutations_are_idempotent(app)


def test_request_fingerprint_separates_method_path_and_body() -> None:
    base = request_sha("POST", "/api/v1/users", b'{"a":1}')
    assert base == request_sha("post", "/api/v1/users", b'{"a":1}')
    assert len({
        base,
        request_sha("PATCH", "/api/v1/users", b'{"a":1}'),
        request_sha("POST", "/api/v1/users/x", b'{"a":1}'),
        request_sha("POST", "/api/v1/users", b'{"a":2}'),
        request_sha("POST", "/api/v1/users?x=1", b'{"a":1}'),
    }) == 5  # fmt: skip
    # length prefixes: moving bytes between path and body changes the hash
    assert request_sha("POST", "/a", b"b") != request_sha("POST", "/ab", b"")


def test_ensure_version() -> None:
    ensure_version(3, 3)
    for expected, code in ((None, "IF_MATCH_REQUIRED"), (2, "VERSION_CONFLICT")):
        with pytest.raises(ApiError) as exc:
            ensure_version(expected, 3)
        assert exc.value.code == code
    assert etag(7) == '"7"'


def _if_match_app() -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/v")
    def v(version: IfMatch) -> dict[str, int | None]:
        return {"version": version}

    return TestClient(app)


@pytest.mark.parametrize(("header", "parsed"), [('"3"', 3), ("3", 3), (' "12" ', 12)])
def test_if_match_header_is_parsed(header: str, parsed: int) -> None:
    assert _if_match_app().get("/v", headers={"If-Match": header}).json() == {"version": parsed}


def test_missing_if_match_is_none() -> None:
    assert _if_match_app().get("/v").json() == {"version": None}


@pytest.mark.parametrize("header", ["*", 'W/"3"', "abc", '"-1"', '"1", "2"', "9" * 19])
def test_malformed_if_match_is_refused(header: str) -> None:
    r = _if_match_app().get("/v", headers={"If-Match": header})
    assert (r.status_code, r.json()["error"]) == (422, "REQUEST_INVALID")
    assert r.json()["gates"][0]["detail"] == "header.If-Match"
