"""/api/v1/users (FN-IAM-05): list, create, change role or active. There is no DELETE (SEC-19).

Clinic admin only (permission matrix, action key FN-IAM-05). The responses never contain the
password or its hash.
"""

from datetime import datetime
from typing import Annotated, Any
import uuid

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field

from jude_api.domain.iam import users
from jude_api.platform.authz import ActionCheck
from jude_api.platform.deps import Clock, Db, Requester
from jude_api.platform.schemas import ERROR_RESPONSES, ErrorResponse

USERS_PREFIX = "/api/v1/users"
Admin = Annotated[Requester, Depends(ActionCheck("FN-IAM-05"))]


class User(BaseModel):
    """FN-IAM-05 output: the account without any credential."""

    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    display_name: str
    login: str
    role: users.Role
    active: bool
    created_at: datetime


class CreateUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(max_length=users.NAME_MAX_LENGTH)
    login: str = Field(min_length=1, max_length=users.LOGIN_MAX_LENGTH)
    role: users.Role
    password: str = Field(min_length=users.PASSWORD_MIN_LENGTH, max_length=1024)


class ChangeUser(BaseModel):
    """Role and/or active. Neither name, login nor password is changed here."""

    model_config = ConfigDict(extra="forbid")
    role: users.Role | None = None
    active: bool | None = None


def _actor(who: Requester) -> users.Actor:
    return users.Actor(who.user_id, who.role, who.ui_session_id)


router = APIRouter(prefix=USERS_PREFIX, responses=ERROR_RESPONSES)


@router.get("", response_model=list[User])
def list_users(who: Admin, conn: Db, response: Response) -> list[dict[str, Any]]:
    result = users.list_users(conn)
    conn.commit()
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "",
    response_model=User,
    status_code=201,
    responses={
        409: {"model": ErrorResponse, "description": "LOGIN_TAKEN"},
        422: {"model": ErrorResponse, "description": "NAME_REQUIRED, REQUEST_INVALID"},
    },
)
def create_user(body: CreateUser, who: Admin, conn: Db) -> dict[str, Any]:
    with conn.transaction():
        return users.create_user(
            conn, _actor(who), display_name=body.display_name, login=body.login,
            role=body.role, password=body.password,
        )  # fmt: skip


@router.patch(
    "/{user_id}",
    response_model=User,
    responses={
        404: {"model": ErrorResponse, "description": "Unknown account"},
        409: {"model": ErrorResponse, "description": "LAST_ADMIN"},
    },
)
def change_user(
    user_id: uuid.UUID, body: ChangeUser, who: Admin, conn: Db, clock: Clock
) -> dict[str, Any]:
    with conn.transaction():
        return users.update_user(
            conn, _actor(who), user_id, role=body.role, active=body.active, now=clock()
        )
