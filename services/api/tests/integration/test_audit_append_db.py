"""IT-FN-AUD-01: audit append on Postgres (TSK-AUD-01-A).

Completion criteria: a scripted session of every event type yields one entry each with all
DATA-09 fields; a rolled-back operation leaves no event. Plus ALG-58: tampering one row is
reported at that row; concurrent appends keep one valid chain.
"""

from collections.abc import Iterator
from contextlib import contextmanager
import threading
from typing import Any
import uuid

import psycopg
import pytest

from jude_api.platform.aud import AuditEvent, append, event_types, verify

pytestmark = pytest.mark.integration

USER = uuid.UUID("00000000-0000-4000-8000-0000000000bb")
CASE = "J-0123ABCD"
UI = "ui-session-00000001"


@contextmanager
def app_conn(url: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(url) as c:
        c.execute("SET ROLE app_rw")
        c.commit()
        yield c


@pytest.fixture
def url(empty_db_url: str) -> str:
    from jude_api.db.migrate import upgrade

    upgrade(empty_db_url)  # fresh chain per test
    return empty_db_url


def events(url: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as c:
        return c.execute(
            "SELECT e.seq, e.type, e.user_id, e.role, e.object_type, e.object_id, e.object_version,"
            " e.case_id, e.at_utc, e.prev_hash, e.hash, e.ui_session_id, s.summary_before,"
            " s.summary_after FROM audit.audit_event e LEFT JOIN audit.audit_summary s USING (seq)"
            " ORDER BY e.seq"
        ).fetchall()


def ev(etype: str, i: int = 1) -> AuditEvent:
    return AuditEvent(
        etype, USER, "technician", object_type="case", object_id=CASE, object_version=i,
        case_id=CASE, summary_before={"v": i - 1}, summary_after={"v": i}, ui_session_id=UI,
    )  # fmt: skip


def test_completion_criterion_every_event_type_once_with_all_data09_fields(url: str) -> None:
    types = sorted(t for t, e in event_types().items() if not e["reserved"])
    with app_conn(url) as c, c.transaction():
        for i, t in enumerate(types, start=1):
            assert append(c, ev(t, i)) == i
        assert c.execute("SELECT current_user").fetchone() == ("app_rw",)  # role restored
    rows = events(url)
    assert [r[1] for r in rows] == types  # exactly one entry per type
    for (
        seq,
        _etype,
        user,
        role,
        otype,
        oid,
        over,
        case_id,
        at,
        prev,
        digest,
        ui,
        before,
        after,
    ) in rows:
        assert (user, role, otype, oid, case_id, ui) == (USER, "technician", "case", CASE, CASE, UI)
        assert over == seq and at.tzinfo is not None and len(digest) == 64
        assert (prev is None) == (seq == 1)
        assert before == {"v": seq - 1} and after == {"v": seq}
    with psycopg.connect(url) as c:
        assert verify(c).first_broken_seq is None and verify(c).checked == len(types)


def test_completion_criterion_rolled_back_operation_leaves_no_event(url: str) -> None:
    with app_conn(url) as c:
        with c.transaction():
            append(c, ev("case.created"))
        with pytest.raises(RuntimeError, match="domain change failed"), c.transaction():
            append(c, ev("case.archived", 2))
            raise RuntimeError("domain change failed")
        with c.transaction():
            append(c, ev("case.consent_ref_set", 2))
    rows = events(url)
    assert [(r[0], r[1]) for r in rows] == [(1, "case.created"), (2, "case.consent_ref_set")]
    with psycopg.connect(url) as c:
        assert verify(c).first_broken_seq is None


def test_tampered_row_is_the_first_broken_link(url: str) -> None:
    with app_conn(url) as c, c.transaction():
        for i in range(1, 6):
            append(c, ev("design.op_changed", i))
    with psycopg.connect(url) as su:  # an attacker with superuser rights edits row 3
        su.execute("ALTER TABLE audit.audit_event DISABLE TRIGGER audit_event_no_update_delete")
        su.execute("UPDATE audit.audit_event SET object_id = 'J-0000000Z' WHERE seq = 3")
        su.execute("ALTER TABLE audit.audit_event ENABLE TRIGGER audit_event_no_update_delete")
        su.commit()
        assert verify(su).first_broken_seq == 3


def test_concurrent_appends_keep_one_valid_chain(url: str) -> None:
    errors: list[BaseException] = []

    def writer(n: int) -> None:
        try:
            with app_conn(url) as c:
                for i in range(n):
                    with c.transaction():
                        append(c, ev("measurement.computed", i + 1))
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(25,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert errors == []
    rows = events(url)
    assert [r[0] for r in rows] == list(range(1, 101))
    with psycopg.connect(url) as c:
        assert verify(c).first_broken_seq is None


def test_app_role_still_cannot_touch_audit_directly(url: str) -> None:
    with app_conn(url) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("SELECT count(*) FROM audit.audit_event")
