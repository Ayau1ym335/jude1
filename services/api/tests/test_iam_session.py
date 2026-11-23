"""UT-FN-IAM-02: deny-by-default start-up check and the cookie gate (no database)."""

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
import pytest

from jude_api.main import API_PREFIX, create_app
from jude_api.platform import deps
from jude_api.platform.iam import api_routes, assert_mutations_need_a_session


def _no_db() -> None:
    raise AssertionError("no database connection without a session cookie")


def test_app_starts_and_every_mutating_route_needs_a_session() -> None:
    app = create_app(db_check=lambda: None, readiness_checks={})
    assert_mutations_need_a_session(app, deps.requester)  # does not raise


def test_a_mutating_route_without_session_check_refuses_to_start() -> None:
    app = FastAPI()

    @app.post(f"{API_PREFIX}/_test/unsafe")
    def unsafe() -> None:
        return None

    @app.delete(f"{API_PREFIX}/_test/safe")
    def safe(who: deps.CurrentRequester) -> None:
        return None

    with pytest.raises(RuntimeError, match=r"POST /api/v1/_test/unsafe"):
        assert_mutations_need_a_session(app, deps.requester)


def test_route_walk_sees_routes_of_included_routers() -> None:
    # Regression: FastAPI keeps an included router as one entry in app.routes; a walk over
    # app.routes alone saw no router route, so both deny-by-default checks checked nothing.
    app = create_app(db_check=lambda: None, readiness_checks={})
    seen = {(m, p) for m, p, _ in api_routes(app)}
    assert {("POST", f"{API_PREFIX}/auth/login"), ("GET", f"{API_PREFIX}/jobs/{{job_id}}")} <= seen


def test_unchecked_mutating_route_in_an_included_router_refuses_to_start() -> None:
    router = APIRouter(prefix=f"{API_PREFIX}/_test")

    @router.patch("/unsafe/{x}")
    def unsafe(x: int) -> None:
        return None

    app = FastAPI()
    app.include_router(router)
    with pytest.raises(RuntimeError, match=r"PATCH /api/v1/_test/unsafe/\{x\}"):
        assert_mutations_need_a_session(app, deps.requester)


def test_missing_cookie_is_401_before_any_database_use() -> None:
    app = create_app(db_check=lambda: None, readiness_checks={})
    app.dependency_overrides[deps.db] = _no_db
    r = TestClient(app).get(f"{API_PREFIX}/jobs/00000000-0000-4000-8000-000000000001")
    assert (r.status_code, r.json()["error"]) == (401, "SESSION_INVALID")
