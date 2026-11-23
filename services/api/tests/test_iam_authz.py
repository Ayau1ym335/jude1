"""UT-FN-IAM-04: the permission matrix and the deny-by-default start-up check (no database)."""

from typing import Annotated

from fastapi import Depends, FastAPI
import pytest

from jude_api.main import create_app
from jude_api.platform.authz import ActionCheck, assert_every_route_authorised, matrix
from jude_api.platform.deps import Requester

ADMIN, TECH = "clinic_admin", "technician"


def test_matrix_shape() -> None:
    m = matrix()
    assert m.roles == (TECH, ADMIN)
    assert len(m.allow) >= 40
    assert all(cells and cells <= {TECH, ADMIN} for cells in m.allow.values())
    assert {("GET", "/api/v1/health"), ("POST", "/api/v1/auth/login")} <= m.public


def test_fr130_admin_has_no_approval_or_export_right() -> None:
    m = matrix()
    for action in ("FN-REV-04", "FN-EXP-01", "FN-EXP-03"):
        assert not m.allowed(ADMIN, action), action
        assert m.allowed(TECH, action), action


def test_fr130_areas() -> None:
    m = matrix()
    admin_only = ("FN-CAS-01", "FN-CAS-03", "FN-IAM-05", "FN-AUD-04", "FN-AUD-05")
    tech_only = ("FN-SCN-01", "FN-SCN-11", "FN-ANA-02", "FN-MEA-01", "FN-DES-02", "FN-DES-07")
    for a in admin_only:
        assert (m.allowed(ADMIN, a), m.allowed(TECH, a)) == (True, False), a
    for a in tech_only:
        assert (m.allowed(ADMIN, a), m.allowed(TECH, a)) == (False, True), a
    assert m.allowed(ADMIN, "FN-CAS-02") and m.allowed(TECH, "FN-CAS-02")


def test_unknown_action_key_is_a_start_up_error() -> None:
    with pytest.raises(KeyError):
        ActionCheck("FN-XYZ-99")
    with pytest.raises(KeyError):
        matrix().allowed(TECH, "FN-XYZ-99")


def test_app_starts_with_every_route_authorised() -> None:
    assert_every_route_authorised(create_app(db_check=lambda: None, readiness_checks={}))


def test_route_without_action_key_refuses_to_start() -> None:
    app = FastAPI()

    @app.get("/api/v1/_test/open")
    def open_route() -> None:
        return None

    @app.get("/api/v1/_test/guarded")
    def guarded(who: Annotated[Requester, Depends(ActionCheck("FN-CAS-02"))]) -> None:
        return None

    with pytest.raises(RuntimeError, match=r"GET /api/v1/_test/open"):
        assert_every_route_authorised(app)
