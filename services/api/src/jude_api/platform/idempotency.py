"""FN-API-01 Idempotent, concurrency-safe mutations (TSK-API-01-A; NFR-07, IF-01, 07 §6.1).

**Idempotency-Key.** Every mutating request that runs under a session carries an
``Idempotency-Key`` header (UUID v4). Without one: 428 IDEMPOTENCY_KEY_REQUIRED. The route
runs its work through ``Idempotent.run``, all in one transaction:

1. an advisory lock on (user, key) serialises concurrent requests with the same key;
2. a stored row for (user, key) is replayed: the stored status and the *exact* response bytes,
   with ``Idempotent-Replayed: true``, without running the handler again. The same key with a
   different request (method, path, body) is refused with 422 IDEMPOTENCY_KEY_REUSED;
3. otherwise the handler runs, and its response is stored in the same transaction as its
   effects: (user, key, request hash, status, body hash, body bytes);
4. the response is sent only after the commit (NFR-07). A client that loses the connection
   after the commit finds the effect on reload, and its retry with the same key gets the
   original response and writes no second audit event.

Only successful (2xx) responses are stored. A refusal rolls the transaction back, leaving
nothing to replay, so a retry after the cause is fixed runs again.

The session check comes first (the key is scoped to the user): 401 / 403 CSRF before 428.
``assert_mutations_are_idempotent`` makes the rule total: a mutating route that needs a session
and does not use ``Idempotent`` refuses to start, like the CSRF check (FN-IAM-02).

**If-Match.** Versioned resources (design version, configuration, ...) compare the client's
``If-Match`` with the current version through ``ensure_version``: missing gives 428
IF_MATCH_REQUIRED, stale gives 409 VERSION_CONFLICT. ``etag(version)`` is the value that
responses send back.
"""

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Annotated, Any, Final
import uuid

from fastapi import Depends, FastAPI, Header, Request, Response
import psycopg
from pydantic import TypeAdapter

from jude_api.platform.deps import CurrentRequester, Requester
from jude_api.platform.errors import ApiError, Gate
from jude_api.platform.iam import SESSIONLESS, depends_on, mutating_routes
from jude_api.platform.schemas import ErrorResponse

KEY_HEADER: Final = "Idempotency-Key"
REPLAYED_HEADER: Final = "Idempotent-Replayed"
IF_MATCH_HEADER: Final = "If-Match"
_ETAG = re.compile(r'^"?([0-9]{1,18})"?$')


def _invalid(header: str) -> ApiError:
    return ApiError(
        "REQUEST_INVALID", gates=[Gate(code="REQUEST_INVALID", detail=f"header.{header}")]
    )


def request_sha(method: str, path: str, body: bytes) -> str:
    h = hashlib.sha256()
    for part in (method.upper().encode(), path.encode(), body):
        h.update(len(part).to_bytes(8, "big"))  # length-prefixed: no ambiguous concatenation
        h.update(part)
    return h.hexdigest()


@dataclass(frozen=True)
class Idempotent:
    who: Requester
    key: str
    request_sha: str

    def run(
        self,
        conn: psycopg.Connection[Any],
        handler: Callable[[], Any],
        *,
        response_model: Any,
        status_code: int = 200,
    ) -> Response:
        """Replay the stored response for this key, or run ``handler`` and store its response."""
        with conn.transaction():
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"idempotency:{self.who.user_id}:{self.key}",),
            )
            row = conn.execute(
                "SELECT request_sha, status_code, body_bytes FROM ops.idempotency_key"
                " WHERE user_id = %s AND key = %s",
                (self.who.user_id, self.key),
            ).fetchone()
            if row is not None:
                stored_sha, stored_status, stored_body = row
                if stored_sha != self.request_sha:
                    raise ApiError("IDEMPOTENCY_KEY_REUSED")
                return _json(bytes(stored_body), stored_status, replayed=True)
            result = handler()
            adapter = TypeAdapter(response_model)  # validate, then serialise, as FastAPI does
            body = adapter.dump_json(adapter.validate_python(result))
            conn.execute(
                """
                INSERT INTO ops.idempotency_key
                       (user_id, key, request_sha, status_code, body_sha, body, body_bytes)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (self.who.user_id, self.key, self.request_sha, status_code,
                 hashlib.sha256(body).hexdigest(), json.dumps(json.loads(body)), body),
            )  # fmt: skip
        return _json(body, status_code, replayed=False)  # sent after the commit (NFR-07)


def _json(body: bytes, status_code: int, *, replayed: bool) -> Response:
    headers = {REPLAYED_HEADER: "true"} if replayed else {}
    return Response(body, status_code=status_code, media_type="application/json", headers=headers)


async def idempotent(
    request: Request,
    who: CurrentRequester,
    raw: Annotated[
        str | None,
        Header(
            alias=KEY_HEADER,
            description=(
                "Required (428 IDEMPOTENCY_KEY_REQUIRED, checked after the session). UUID v4"
                " chosen by the client per operation; send it again to retry (FN-API-01)."
            ),
        ),
    ] = None,
) -> Idempotent:
    if raw is None:
        raise ApiError("IDEMPOTENCY_KEY_REQUIRED")
    try:
        key = uuid.UUID(raw)
    except ValueError:
        raise _invalid(KEY_HEADER) from None
    if key.version != 4 or str(key) != raw.lower():
        raise _invalid(KEY_HEADER)
    path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return Idempotent(who, str(key), request_sha(request.method, path, await request.body()))


IdempotentRequest = Annotated[Idempotent, Depends(idempotent)]

# For the ``responses=`` of every idempotent route (OpenAPI only).
IDEMPOTENT_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    428: {"model": ErrorResponse, "description": "IDEMPOTENCY_KEY_REQUIRED"},
    422: {"model": ErrorResponse, "description": "IDEMPOTENCY_KEY_REUSED, REQUEST_INVALID"},
}


def assert_mutations_are_idempotent(app: FastAPI) -> None:
    """Deny by default: a session-bound mutating route without ``Idempotent`` cannot start."""
    missing = [
        f"{method} {path}"
        for method, path, dependant in mutating_routes(app)
        if (method, path) not in SESSIONLESS and not depends_on(dependant, idempotent)
    ]
    if missing:
        raise RuntimeError(f"mutating routes without Idempotency-Key: {', '.join(missing)}")


# --- If-Match (optimistic concurrency on versioned resources) -------------------------------


def if_match(
    raw: Annotated[
        str | None,
        Header(alias=IF_MATCH_HEADER, description="Version the edit is based on (ETag)"),
    ] = None,
) -> int | None:
    if raw is None:
        return None
    m = _ETAG.fullmatch(raw.strip())
    if m is None:
        raise _invalid(IF_MATCH_HEADER)
    return int(m.group(1))


IfMatch = Annotated[int | None, Depends(if_match)]


def ensure_version(expected: int | None, current: int) -> None:
    """Call with the row locked (SELECT ... FOR UPDATE) so the check holds until the commit."""
    if expected is None:
        raise ApiError("IF_MATCH_REQUIRED")
    if expected != current:
        raise ApiError("VERSION_CONFLICT")


def etag(version: int) -> str:
    return f'"{version}"'
