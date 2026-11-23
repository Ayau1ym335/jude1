"""FN-IAM-02 Validate session and enforce idle timeout (TSK-IAM-02-A; SEC-06, SEC-20, IDR-08).

Runs before every authenticated endpoint (the ``requester`` dependency in ``deps``):

1. session looked up by SHA-256 of the cookie token; absent -> 401 SESSION_INVALID;
2. idle longer than SD-02 (security.json) -> session deleted, 401 SESSION_EXPIRED;
3. user deactivated -> session deleted, 401 SESSION_INVALID;
4. POST / PUT / PATCH / DELETE: X-CSRF-Token compared in constant time with the session's
   token hash -> 403 CSRF_INVALID (SEC-20);
5. last_seen_at refreshed at most once per ``last_seen_write_interval_seconds``;
6. the request gets {user_id, role, session_id, ui_session_id}.

``assert_mutations_need_a_session`` makes the CSRF rule total: every mutating route except the
ones in ``SESSIONLESS`` must depend on ``requester``, or the application refuses to start.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
import hmac
from typing import Any
import uuid

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts
import psycopg

from jude_api.platform.errors import ApiError
from jude_api.platform.security_config import SecurityConfig

SESSION_COOKIE = "jude_session"
CSRF_HEADER = "X-CSRF-Token"
MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SESSIONLESS = frozenset(
    {
        ("POST", "/api/v1/auth/login"),  # no session exists yet
        ("POST", "/api/v1/auth/logout"),  # idempotent; checks session + CSRF itself (FN-IAM-03)
    }
)


@dataclass(frozen=True)
class Requester:
    user_id: uuid.UUID
    role: str
    session_id: str
    ui_session_id: str | None


def validate_session(
    conn: psycopg.Connection[Any],
    session_hash: str,
    method: str,
    csrf_hash: str | None,
    cfg: SecurityConfig,
    now: datetime,
) -> Requester:
    """Steps 1-6; commits its own writes (expiry delete, last_seen refresh)."""
    row = conn.execute(
        "SELECT s.user_id, s.csrf_hash, s.last_seen_at, s.ui_session_id, u.role, u.active"
        ' FROM governance.session s JOIN governance."user" u ON u.id = s.user_id'
        " WHERE s.id = %s",
        (session_hash,),
    ).fetchone()
    if row is None:
        conn.commit()
        raise ApiError("SESSION_INVALID")
    user_id, stored_csrf, last_seen, ui_session_id, role, active = row
    if now - last_seen > timedelta(seconds=cfg.idle_timeout_seconds) or not active:
        conn.execute("DELETE FROM governance.session WHERE id = %s", (session_hash,))
        conn.commit()
        raise ApiError("SESSION_EXPIRED" if active else "SESSION_INVALID")
    if method.upper() in MUTATING and (
        csrf_hash is None or not hmac.compare_digest(csrf_hash, stored_csrf)
    ):
        conn.commit()
        raise ApiError("CSRF_INVALID")
    if now - last_seen >= timedelta(seconds=cfg.last_seen_write_interval_seconds):
        conn.execute(
            "UPDATE governance.session SET last_seen_at = %s WHERE id = %s", (now, session_hash)
        )
    conn.commit()
    return Requester(
        user_id=user_id, role=role, session_id=session_hash, ui_session_id=ui_session_id
    )


def _depends_on(dependant: Dependant, target: Any) -> bool:
    return any(d.call is target or _depends_on(d, target) for d in dependant.dependencies)


def api_routes(app: FastAPI) -> Iterator[tuple[str, str, Dependant]]:
    """Every (method, full path, dependant) of the app, including routes of included routers.

    FastAPI >= 0.16x keeps an included router as one ``_IncludedRouter`` entry in
    ``app.routes``. A plain walk over ``app.routes`` therefore sees none of the router routes,
    and a deny-by-default check built on it checks nothing. ``iter_route_contexts`` (public
    API) flattens them with the effective path and the dependant that includes router-level
    dependencies.
    """
    for ctx in iter_route_contexts(app.routes):
        if isinstance(ctx.original_route, APIRoute):
            for method in sorted(ctx.methods or ()):
                yield method, ctx.path or "", ctx.dependant


def mutating_routes(app: FastAPI) -> Iterable[tuple[str, str, Dependant]]:
    for method, path, dependant in api_routes(app):
        if method in MUTATING:
            yield method, path, dependant


def assert_mutations_need_a_session(app: FastAPI, requester: Any) -> None:
    """Deny by default: a mutating route without the session (and CSRF) check cannot start."""
    missing = [
        f"{method} {path}"
        for method, path, dependant in mutating_routes(app)
        if (method, path) not in SESSIONLESS and not _depends_on(dependant, requester)
    ]
    if missing:
        raise RuntimeError(f"mutating routes without session/CSRF check: {', '.join(missing)}")
