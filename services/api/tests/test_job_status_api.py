"""UT-FN-JOB-03: the job status route without a database (auth placeholder, validation)."""

import uuid

from fastapi.testclient import TestClient

from jude_api.main import create_app
from jude_api.platform import deps
from jude_api.platform.job_routes import JOBS_PREFIX, _summary

JOB = "6f1c4c6e-0000-4000-8000-000000000001"


def _no_db() -> None:
    raise AssertionError("an unauthenticated request must not open a database connection")


def client() -> TestClient:
    app = create_app(db_check=lambda: None, readiness_checks={})
    app.dependency_overrides[deps.db] = _no_db
    return TestClient(app)


def test_route_is_part_of_the_v1_contract() -> None:
    assert JOBS_PREFIX.startswith("/api/v1/")


def test_until_sessions_exist_every_request_is_refused_401() -> None:
    resp = client().get(f"{JOBS_PREFIX}/{JOB}")
    assert resp.status_code == 401
    assert resp.json()["error"] == "SESSION_INVALID"


def who() -> deps.Requester:
    return deps.Requester(
        user_id=uuid.UUID(int=1), role="technician", session_id="0" * 64, ui_session_id=None
    )


def test_malformed_job_id_is_a_validation_error() -> None:
    app = create_app(db_check=lambda: None, readiness_checks={})
    app.dependency_overrides[deps.requester] = who
    app.dependency_overrides[deps.db] = lambda: None  # validation fails before any query
    resp = TestClient(app).get(f"{JOBS_PREFIX}/not-a-uuid")
    assert resp.status_code == 422 and resp.json()["error"] == "REQUEST_INVALID"


def test_default_case_access_denies() -> None:
    assert deps.case_access()(who(), "J-00000000") is False


def test_summary_needs_the_envelope_fields() -> None:
    assert _summary(None) is None
    assert _summary({"op_type": "x"}) is None
    env = {
        "op_type": "t",
        "op_version": 1,
        "status": "ok",
        "reason_code": None,
        "output_names": ["mesh"],
        "report": {"n": 1},
        "lib_versions": {"numpy": "2"},
    }
    assert _summary(env) == {
        k: env[k]
        for k in ("op_type", "op_version", "status", "reason_code", "output_names", "report")
    }
