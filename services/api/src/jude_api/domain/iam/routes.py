"""/api/v1/auth routes (FN-IAM-01). Session validation and logout follow (FN-IAM-02/03)."""

from datetime import UTC
from typing import Literal
import uuid

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from jude_api.domain.iam.login import LoginSuccess, authenticate, logout, token_hash
from jude_api.platform.deps import Clock, Config, Db
from jude_api.platform.errors import ApiError, Gate
from jude_api.platform.iam import CSRF_HEADER, SESSION_COOKIE
from jude_api.platform.schemas import ERROR_RESPONSES, ErrorResponse

AUTH_PREFIX = "/api/v1/auth"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)


class SessionUser(BaseModel):
    id: uuid.UUID
    display_name: str
    role: Literal["technician", "clinic_admin"]


class LoginResponse(BaseModel):
    """The session token travels only in the httpOnly cookie; the CSRF token in this body."""

    csrf_token: str
    user: SessionUser


router = APIRouter(prefix=AUTH_PREFIX, responses=ERROR_RESPONSES)


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        401: {"model": ErrorResponse, "description": "BAD_CREDENTIALS"},
        423: {
            "model": ErrorResponse,
            "description": "ACCOUNT_LOCKED (gate detail: unlock time UTC)",
        },
    },
)
def login(
    body: LoginRequest, conn: Db, cfg: Config, clock: Clock, response: Response
) -> LoginResponse:
    with conn.transaction():
        outcome = authenticate(conn, body.login, body.password, cfg, clock())
    if not isinstance(outcome, LoginSuccess):  # committed: failure row + audit event stay
        gates = []
        if outcome.locked_until is not None:
            gates = [
                Gate(code="ACCOUNT_LOCKED", detail=outcome.locked_until.astimezone(UTC).isoformat())
            ]
        raise ApiError(outcome.code, gates=gates)
    response.set_cookie(
        SESSION_COOKIE,
        outcome.session_token,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(
        csrf_token=outcome.csrf_token,
        user=SessionUser.model_validate(
            {"id": outcome.user_id, "display_name": outcome.display_name, "role": outcome.role}
        ),
    )


@router.post(
    "/logout",
    status_code=204,
    responses={403: {"model": ErrorResponse, "description": "CSRF_INVALID (live session)"}},
)
def logout_route(request: Request, conn: Db) -> Response:
    """FN-IAM-03: delete the session, emit auth.logout, expire the cookie. Idempotent (204)."""
    token = request.cookies.get(SESSION_COOKIE)
    outcome = "no_session"
    if token:
        csrf = request.headers.get(CSRF_HEADER)
        with conn.transaction():
            outcome = logout(conn, token_hash(token), token_hash(csrf) if csrf else None)
    if outcome == "csrf_invalid":
        raise ApiError("CSRF_INVALID")
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return response
