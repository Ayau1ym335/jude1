"""Correlation IDs: one ID follows a user action UI -> API -> job -> kernel result (XC-FND-11).

- UI: sends header X-Correlation-ID (the generated client of XC-FND-06 adds it).
- API: accepts a well-formed incoming ID or creates one; returns it in the response header
  and in every DS-24 error body; puts it into job payloads (``inject``).
- Worker: reads it from the payload (``extract``) and binds it while the job runs; the job
  result envelope carries it next to the kernel OpResult report.

IDs are opaque tokens, never derived from user data.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
import re
import uuid

HEADER = "X-Correlation-ID"
PAYLOAD_KEY = "correlation_id"
_VALID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{7,63}$")

_current: ContextVar[str | None] = ContextVar("jude_correlation_id", default=None)


def new_id() -> str:
    return uuid.uuid4().hex


def accept(candidate: str | None) -> str:
    """Return ``candidate`` if it is a well-formed ID, otherwise a fresh one."""
    if candidate is not None and _VALID.fullmatch(candidate):
        return candidate
    return new_id()


def current() -> str | None:
    return _current.get()


@contextmanager
def bound(correlation_id: str) -> Iterator[str]:
    """Bind ``correlation_id`` for the current context (request or job)."""
    token = _current.set(correlation_id)
    try:
        yield correlation_id
    finally:
        _current.reset(token)


def inject(payload: Mapping[str, object], correlation_id: str | None = None) -> dict[str, object]:
    """Copy of a job payload carrying the correlation ID (the bound one by default)."""
    cid = correlation_id or current() or new_id()
    return {**payload, PAYLOAD_KEY: cid}


def extract(payload: Mapping[str, object]) -> str:
    """Correlation ID of a job payload; a fresh one if absent or malformed."""
    value = payload.get(PAYLOAD_KEY)
    return accept(value if isinstance(value, str) else None)
