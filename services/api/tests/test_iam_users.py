"""UT-FN-IAM-05: account management routes, request rules, matrix cells (no database)."""

from typing import Any

from pydantic import ValidationError
import pytest

from jude_api.domain.iam import bootstrap, users
from jude_api.domain.iam.user_routes import USERS_PREFIX, ChangeUser, CreateUser, User
from jude_api.main import create_app
from jude_api.platform.authz import matrix
from jude_api.platform.iam import api_routes

VALID = {"display_name": "A. B.", "login": "ab", "role": "technician", "password": "x" * 12}


def test_no_api_path_deletes_a_user() -> None:
    app = create_app(db_check=lambda: None, readiness_checks={})
    routes = {(m, p) for m, p, _ in api_routes(app)}
    assert {
        ("GET", USERS_PREFIX),
        ("POST", USERS_PREFIX),
        ("PATCH", f"{USERS_PREFIX}/{{user_id}}"),
    } <= routes
    assert not [p for m, p, _ in api_routes(app) if m == "DELETE"]


def test_only_the_clinic_admin_manages_accounts() -> None:
    m = matrix()
    assert m.allowed("clinic_admin", "FN-IAM-05") and not m.allowed("technician", "FN-IAM-05")


@pytest.mark.parametrize(
    "change",
    [
        {"password": "x" * (users.PASSWORD_MIN_LENGTH - 1)},
        {"login": ""},
        {"login": "x" * (users.LOGIN_MAX_LENGTH + 1)},
        {"display_name": "x" * (users.NAME_MAX_LENGTH + 1)},
        {"role": "admin"},
        {"password_hash": "$argon2id$..."},
    ],
)
def test_create_request_rules(change: dict[str, Any]) -> None:
    CreateUser.model_validate(VALID)
    with pytest.raises(ValidationError):
        CreateUser.model_validate({**VALID, **change})


@pytest.mark.parametrize("body", [{"login": "x"}, {"display_name": "x"}, {"password": "x" * 12}])
def test_patch_changes_only_role_and_active(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ChangeUser.model_validate(body)


def test_user_output_has_no_credential() -> None:
    assert not [f for f in User.model_fields if "pass" in f or "hash" in f]


@pytest.mark.parametrize(
    ("login", "ok"),
    [("tech1", True), ("a.b-c_d@clinic", True), ("a b", False), ("тех", False),
     ("-lead", False), ("x" * 64, True), ("x" * 65, False)],
)  # fmt: skip
def test_login_pattern(login: str, ok: bool) -> None:
    assert bool(users.LOGIN_RE.fullmatch(login)) is ok


def test_bootstrap_actor_is_the_system_not_an_account() -> None:
    assert (bootstrap.SYSTEM.user_id, bootstrap.SYSTEM.role) == (None, "system")
