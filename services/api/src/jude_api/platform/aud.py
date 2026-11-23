"""FN-AUD-01 Append audit event (TSK-AUD-01-A; ALG-58, ADR-012, DATA-09, DATA-19, FR-120).

Every state change is recorded attributably and tamper-evidently **in the caller's
transaction**: a rolled-back operation leaves no event (INV-09).

Hash chain (ALG-58):

    h_0 = SHA-256(b"JUDE-AUDIT-GENESIS")
    h_n = SHA-256(h_{n-1} || JCS(core_n))        (h as the raw 32-byte digest)
    core = {seq, type, user_id, role, object_type, object_id, object_version, case_id, at_utc}

``case_id`` is part of the core in addition to ALG-58's list, so re-attributing an event to
another case is also detected. The before/after summary (erasable, IDR-06) and
``ui_session_id`` (DATA-19) are stored outside the hashed core. JCS (RFC 8785) for this core
is sorted keys, no whitespace, UTF-8; values are only strings, integers and null, and
timestamps are UTC ``YYYY-MM-DDTHH:MM:SS.ffffffZ``.

Database roles (ADR-012). ``app_rw`` has no access to the audit schema. The append switches
to ``audit_append`` for the duration of the call (``SET LOCAL ROLE``) and back, so the
login role must be a member of both. The SECURITY DEFINER ``audit.append_event`` locks the
chain head and refuses an append that does not continue it. Appends are serialised by a
transaction-level advisory lock taken before the head is read (``audit_append`` may not lock
the head row itself); appends already queue on the head row until commit, so this only moves
the queue in front of the read. A serialization_failure is still retried inside a savepoint.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Final
import uuid

import psycopg
from psycopg import errors, pq
from psycopg.types.json import Jsonb

GENESIS: Final = hashlib.sha256(b"JUDE-AUDIT-GENESIS").digest()
APPEND_ROLE: Final = "audit_append"
MAX_RETRIES: Final = 3
CHAIN_LOCK_KEY: Final = 0x4A55444541554454  # "JUDEAUDT", pg_advisory_xact_lock key
ROLE_RE: Final = re.compile(r"^[a-z_]{1,32}$")
CATALOGUE: Final = Path(__file__).resolve().parent / "audit_events.json"


@cache
def event_types() -> Mapping[str, Mapping[str, Any]]:
    types: Mapping[str, Mapping[str, Any]] = json.loads(CATALOGUE.read_text(encoding="utf-8"))[
        "types"
    ]
    return types


@dataclass(frozen=True)
class AuditEvent:
    """DATA-09 fields supplied by the caller; seq, time and hashes are added by ``append``."""

    type: str
    user_id: uuid.UUID | None
    role: str | None
    object_type: str | None = None
    object_id: str | None = None
    object_version: int | None = None
    case_id: str | None = None
    summary_before: Mapping[str, Any] | None = None
    summary_after: Mapping[str, Any] | None = None
    ui_session_id: str | None = None

    def __post_init__(self) -> None:
        entry = event_types().get(self.type)
        if entry is None:
            raise ValueError(f"audit event type {self.type!r} is not in the catalogue")
        if entry["reserved"]:
            raise ValueError(f"audit event type {self.type!r} is reserved (AI-10)")
        if self.role is not None and not ROLE_RE.fullmatch(self.role):
            raise ValueError("role must be a role key")


def utc_text(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def core(seq: int, ev: Mapping[str, Any], at_utc: datetime) -> dict[str, Any]:
    return {
        "seq": seq,
        "type": ev["type"],
        "user_id": str(ev["user_id"]) if ev["user_id"] is not None else None,
        "role": ev["role"],
        "object_type": ev["object_type"],
        "object_id": ev["object_id"],
        "object_version": ev["object_version"],
        "case_id": ev["case_id"],
        "at_utc": utc_text(at_utc),
    }


def jcs(obj: Mapping[str, Any]) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def chain_hash(prev_hex: str | None, core_obj: Mapping[str, Any]) -> str:
    prev = bytes.fromhex(prev_hex) if prev_hex is not None else GENESIS
    return hashlib.sha256(prev + jcs(core_obj)).hexdigest()


def append(conn: psycopg.Connection[Any], event: AuditEvent, *, now: datetime | None = None) -> int:
    """Append ``event`` in the caller's open transaction; returns its seq."""
    if conn.info.transaction_status != pq.TransactionStatus.INTRANS:
        raise RuntimeError("audit append needs the caller's open transaction")
    at = (now or datetime.now(UTC)).astimezone(UTC)  # timestamptz keeps microseconds
    fields = {
        "type": event.type, "user_id": event.user_id, "role": event.role,
        "object_type": event.object_type, "object_id": event.object_id,
        "object_version": event.object_version, "case_id": event.case_id,
    }  # fmt: skip
    previous_role = conn.execute("SELECT current_user").fetchone()
    assert previous_role is not None  # noqa: S101 - always one row
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (CHAIN_LOCK_KEY,))  # held until commit
    conn.execute(f"SET LOCAL ROLE {APPEND_ROLE}")
    try:
        for _attempt in range(MAX_RETRIES):
            try:
                with conn.transaction():  # savepoint: a lost race is retried, not fatal
                    head = conn.execute(
                        "SELECT last_seq, last_hash FROM audit.chain_head"
                    ).fetchone()
                    assert head is not None  # noqa: S101 - single-row table
                    seq = int(head[0]) + 1
                    prev = head[1]
                    digest = chain_hash(prev, core(seq, fields, at))
                    conn.execute(
                        "SELECT audit.append_event(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
                        " %s, %s, %s)",
                        (seq, event.type, event.user_id, event.role, event.object_type,
                         event.object_id, event.object_version, event.case_id, at, prev, digest,
                         Jsonb(dict(event.summary_before)) if event.summary_before else None,
                         Jsonb(dict(event.summary_after)) if event.summary_after else None,
                         event.ui_session_id),
                    )  # fmt: skip
                    return seq
            except errors.SerializationFailure:
                continue
        raise RuntimeError("audit chain head contended too long")
    finally:
        conn.execute(f"SET LOCAL ROLE {previous_role[0]}")


@dataclass(frozen=True)
class Verification:
    checked: int
    first_broken_seq: int | None


def verify(conn: psycopg.Connection[Any]) -> Verification:
    """Recompute the chain (ALG-58); report the first broken link or seq gap (FN-AUD-03)."""
    prev: str | None = None
    expected = 1
    checked = 0
    cur = conn.execute(
        "SELECT seq, type, user_id, role, object_type, object_id, object_version, case_id,"
        " at_utc, prev_hash, hash FROM audit.audit_event ORDER BY seq"
    )
    for seq, etype, user, role, otype, oid, over, case_id, at, prev_hash, digest in cur:
        fields = {"type": etype, "user_id": user, "role": role, "object_type": otype,
                  "object_id": oid, "object_version": over, "case_id": case_id}  # fmt: skip
        if (
            seq != expected
            or prev_hash != prev
            or chain_hash(prev, core(seq, fields, at)) != digest
        ):
            return Verification(checked, seq)
        prev, expected, checked = digest, expected + 1, checked + 1
    head = conn.execute("SELECT last_seq, last_hash FROM audit.chain_head").fetchone()
    if head is not None and (head[0] != checked or head[1] != prev):
        return Verification(checked, checked + 1)
    return Verification(checked, None)
