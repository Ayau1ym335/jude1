"""Request dependencies shared by /api/v1 routes: database, clock, security config, requester.

- ``db``: one psycopg connection per request, switched to the least-privilege role ``app_rw``
  (SCHEMA.md). A pool replaces the per-request connect when load needs it.
- ``clock`` / ``config``: current UTC time and SD-01/SD-02 settings; overridden in tests.
- ``requester``: the authenticated user (FN-IAM-02, ``platform.iam``). A request without the
  session cookie is refused before any database connection is opened.
- ``case_access``: may the requester see a case? The permission matrix and case scope are
  TSK-IAM-04-A; until then the default denies (owners still see their own jobs).
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
import hashlib
import os
from typing import Annotated, Protocol

from fastapi import Depends, Request
import psycopg

from jude_api.platform.errors import ApiError
from jude_api.platform.iam import CSRF_HEADER, SESSION_COOKIE, Requester, validate_session
from jude_api.platform.security_config import SecurityConfig, security_config

CONNECT_TIMEOUT_S = 2
APP_ROLE = "app_rw"

__all__ = ["Requester"]


def db() -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    with psycopg.connect(
        os.environ["JUDE_DATABASE_URL"], connect_timeout=CONNECT_TIMEOUT_S
    ) as conn:
        conn.execute(f"SET ROLE {APP_ROLE}")
        conn.commit()
        yield conn


def utc_now() -> datetime:
    return datetime.now(UTC)


def clock() -> Callable[[], datetime]:
    return utc_now  # overridden in tests


Db = Annotated[psycopg.Connection[tuple[object, ...]], Depends(db)]
Clock = Annotated[Callable[[], datetime], Depends(clock)]
Config = Annotated[SecurityConfig, Depends(security_config)]


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8", "surrogatepass")).hexdigest()


def session_token(request: Request) -> str:
    """The session cookie, or 401 before anything else (no DB connection is opened)."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise ApiError("SESSION_INVALID")
    return token


def requester(
    request: Request,
    token: Annotated[str, Depends(session_token)],
    conn: Db,
    cfg: Config,
    now: Clock,
) -> Requester:
    csrf = request.headers.get(CSRF_HEADER)
    return validate_session(
        conn, _sha(token), request.method, _sha(csrf) if csrf else None, cfg, now()
    )


class CaseAccess(Protocol):
    def __call__(self, who: Requester, case_id: str) -> bool: ...


def deny_all_cases(who: Requester, case_id: str) -> bool:
    return False


def case_access() -> CaseAccess:
    return deny_all_cases  # replaced by the permission matrix in TSK-IAM-04-A


CurrentRequester = Annotated[Requester, Depends(requester)]
CaseAccessCheck = Annotated[CaseAccess, Depends(case_access)]
