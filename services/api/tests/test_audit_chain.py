"""UT-FN-AUD-01: chain hash, canonical core, event-type rules (no database)."""

from datetime import UTC, datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace
import uuid

from psycopg import pq
import pytest

from jude_api.platform.aud import (
    GENESIS,
    AuditEvent,
    append,
    chain_hash,
    core,
    event_types,
    jcs,
    utc_text,
)

USER = uuid.UUID("00000000-0000-4000-8000-0000000000aa")
AT = datetime(2026, 11, 23, 10, 0, 0, 123456, tzinfo=UTC)
FIELDS = {"type": "case.created", "user_id": USER, "role": "clinic_admin", "object_type": "case",
          "object_id": "J-0123ABCD", "object_version": 1, "case_id": "J-0123ABCD"}  # fmt: skip


def test_genesis_and_first_link() -> None:
    assert GENESIS == hashlib.sha256(b"JUDE-AUDIT-GENESIS").digest()
    c = core(1, FIELDS, AT)
    assert chain_hash(None, c) == hashlib.sha256(GENESIS + jcs(c)).hexdigest()
    h1 = chain_hash(None, c)
    assert (
        chain_hash(h1, core(2, FIELDS, AT))
        == hashlib.sha256(bytes.fromhex(h1) + jcs(core(2, FIELDS, AT))).hexdigest()
    )


def test_golden_vector() -> None:
    """Frozen: changing the canonical form or the hash rule breaks every stored chain."""
    assert jcs(core(1, FIELDS, AT)) == (
        b'{"at_utc":"2026-11-23T10:00:00.123456Z","case_id":"J-0123ABCD","object_id":"J-0123ABCD",'
        b'"object_type":"case","object_version":1,"role":"clinic_admin","seq":1,'
        b'"type":"case.created","user_id":"00000000-0000-4000-8000-0000000000aa"}'
    )
    assert chain_hash(None, core(1, FIELDS, AT)) == GOLDEN


GOLDEN = hashlib.sha256(
    hashlib.sha256(b"JUDE-AUDIT-GENESIS").digest()
    + b'{"at_utc":"2026-11-23T10:00:00.123456Z","case_id":"J-0123ABCD","object_id":"J-0123ABCD",'
    b'"object_type":"case","object_version":1,"role":"clinic_admin","seq":1,'
    b'"type":"case.created","user_id":"00000000-0000-4000-8000-0000000000aa"}'
).hexdigest()


def test_timestamps_are_utc_with_microseconds() -> None:
    almaty = timezone(timedelta(hours=5))
    assert utc_text(AT.astimezone(almaty)) == "2026-11-23T10:00:00.123456Z"
    assert utc_text(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-01-01T00:00:00.000000Z"


def test_every_core_field_changes_the_hash() -> None:
    base = chain_hash(None, core(1, FIELDS, AT))
    changes = [
        ("type", "case.archived"), ("user_id", uuid.UUID(int=2)), ("role", "technician"),
        ("object_type", "scan"), ("object_id", "x"), ("object_version", 2),
        ("case_id", "J-0000000Z"),
    ]  # fmt: skip
    for key, other in changes:
        assert chain_hash(None, core(1, {**FIELDS, key: other}, AT)) != base, key
    assert chain_hash(None, core(2, FIELDS, AT)) != base
    assert chain_hash(None, core(1, FIELDS, AT + timedelta(microseconds=1))) != base


def test_catalogue_and_reserved_types() -> None:
    assert len(event_types()) >= 50
    with pytest.raises(ValueError, match="not in the catalogue"):
        AuditEvent("case.teleported", USER, "technician")
    with pytest.raises(ValueError, match="reserved"):
        AuditEvent("ai.model.enabled", USER, "technician")
    with pytest.raises(ValueError, match="role"):
        AuditEvent("case.created", USER, "Not A Role")


def test_append_needs_an_open_transaction() -> None:
    fake = SimpleNamespace(info=SimpleNamespace(transaction_status=pq.TransactionStatus.IDLE))
    with pytest.raises(RuntimeError, match="open transaction"):
        append(fake, AuditEvent("case.created", USER, "clinic_admin"))  # type: ignore[arg-type]
