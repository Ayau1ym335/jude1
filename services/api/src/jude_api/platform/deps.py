"""Request dependencies shared by /api/v1 routes: database connection and the requester.

- ``db``: one psycopg connection per request, switched to the least-privilege role ``app_rw``
  (SCHEMA.md); committed by the route, rolled back on any error. A pool replaces the
  per-request connect when load needs it.
- ``requester``: the authenticated user. Session validation is TSK-IAM-02-A; until it lands
  this dependency refuses every request with 401 SESSION_INVALID, so no route that needs a
  user can be reached unauthenticated by accident. Tests override it.
- ``case_access``: may the requester see a case? The permission matrix and case scope are
  TSK-IAM-04-A; until then the default denies (owners still see their own jobs).
"""

from collections.abc import Iterator
from dataclasses import dataclass
import os
from typing import Annotated, Protocol
import uuid

from fastapi import Depends
import psycopg

from jude_api.platform.errors import ApiError

CONNECT_TIMEOUT_S = 2
APP_ROLE = "app_rw"


def db() -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    with psycopg.connect(
        os.environ["JUDE_DATABASE_URL"], connect_timeout=CONNECT_TIMEOUT_S
    ) as conn:
        conn.execute(f"SET ROLE {APP_ROLE}")
        conn.commit()
        yield conn


@dataclass(frozen=True)
class Requester:
    user_id: uuid.UUID


def requester() -> Requester:
    raise ApiError("SESSION_INVALID")  # replaced by session validation in TSK-IAM-02-A


class CaseAccess(Protocol):
    def __call__(self, who: Requester, case_id: str) -> bool: ...


def deny_all_cases(who: Requester, case_id: str) -> bool:
    return False


def case_access() -> CaseAccess:
    return deny_all_cases  # replaced by the permission matrix in TSK-IAM-04-A


Db = Annotated[psycopg.Connection[tuple[object, ...]], Depends(db)]
CurrentRequester = Annotated[Requester, Depends(requester)]
CaseAccessCheck = Annotated[CaseAccess, Depends(case_access)]
