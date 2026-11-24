"""IT-FN-REV-06: design version state machine in the database (TSK-REV-06-A; FR-091, FR-056,
SAF-08).

Completion criterion: an edit after approval gives a new version that is not approved; the old
approval is unchanged.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import hashlib
import itertools
import threading
from typing import Any
import uuid

import psycopg
from psycopg import errors
import pytest

from jude_api.domain.rev.states import Event, Status, status_changes
from jude_api.domain.rev.versions import draft_for_edit, transition
from jude_api.platform.errors import ApiError

pytestmark = pytest.mark.integration

USER = uuid.UUID("00000000-0000-4000-8000-0000000000e1")
OTHER = uuid.UUID("00000000-0000-4000-8000-0000000000e2")
IDENTITY = [float(i % 5 == 0) for i in range(16)]  # row-major 4x4 identity
PATHS: dict[Status, list[Event]] = {
    Status.DRAFT: [],
    Status.SAVED: [Event.SAVE],
    Status.REVIEWED_PASS: [Event.SAVE, Event.REVIEW_PASSED],
    Status.REVIEWED_FAIL: [Event.SAVE, Event.REVIEW_FAILED],
    Status.APPROVED: [Event.SAVE, Event.REVIEW_PASSED, Event.APPROVE],
    Status.REJECTED: [Event.SAVE, Event.REJECT],
    Status.EXPORTED: [Event.SAVE, Event.REVIEW_PASSED, Event.APPROVE, Event.EXPORT],
    Status.SUPERSEDED: [Event.SUPERSEDE],
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@contextmanager
def app_conn(url: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(url) as c:
        c.execute("SET ROLE app_rw")
        c.commit()
        yield c


class Seed:
    """Case -> scan -> frame -> config -> measurement set; designs on demand."""

    def __init__(self, url: str) -> None:
        self.url = url
        with psycopg.connect(url) as c:
            c.execute("""INSERT INTO clinical."case" (case_id, status, created_by)
                         VALUES ('J-0123ABCD', 'active', %s)""", (USER,))  # fmt: skip
            self.scan = c.execute(
                """INSERT INTO geometry.scan (case_id, status, original_sha, file_name, size_bytes,
                       uploaded_by) VALUES ('J-0123ABCD', 'uploaded', %s, 'T1.stl', 84, %s)
                   RETURNING id""",
                (sha("scan"), USER),
            ).fetchone()[0]  # type: ignore[index]
            self.frame = c.execute(
                """INSERT INTO geometry.frame (scan_id, from_frame, to_frame, matrix, det,
                       provenance, created_by) VALUES (%s, 'F_scan', 'F_anat', %s, 1.0, '{}', %s)
                   RETURNING id""",
                (self.scan, IDENTITY, USER),
            ).fetchone()[0]  # type: ignore[index]
            c.execute(
                """INSERT INTO governance.config_version (version, document, test_only, state,
                       controlled, published_by) VALUES (1, '{}', true, 'active', false, %s)""",
                (USER,),
            )
            self.measurements = c.execute(
                """INSERT INTO geometry.measurement_set (frame_id, config_version,
                       landmark_set_sha, source_mesh_sha, software_version, created_by)
                   VALUES (%s, 1, %s, %s, '0.0.0', %s) RETURNING id""",
                (self.frame, sha("landmarks"), sha("mesh"), USER),
            ).fetchone()[0]  # type: ignore[index]

    def version(self, ops: int = 2) -> uuid.UUID:
        """A new design with version 1 as a draft carrying ``ops`` operations."""
        with psycopg.connect(self.url) as c:
            design = c.execute(
                """INSERT INTO geometry.design (case_id, scan_id, frame_id, created_by)
                   VALUES ('J-0123ABCD', %s, %s, %s) RETURNING id""",
                (self.scan, self.frame, USER),
            ).fetchone()[0]  # type: ignore[index]
            vid = c.execute(
                """INSERT INTO geometry.design_version (design_id, number, status, scan_sha,
                       frame_id, config_version, params_sha, geometry_sha, created_by)
                   VALUES (%s, 1, 'draft', %s, %s, 1, %s, %s, %s) RETURNING id""",
                (design, sha("scan"), self.frame, sha("params"), sha("geom"), USER),
            ).fetchone()[0]  # type: ignore[index]
            for seq in range(1, ops + 1):
                c.execute(
                    """INSERT INTO geometry.operation (design_version_id, seq, type, op_version,
                           params, enabled, status, created_by)
                       VALUES (%s, %s, 'offset.uniform_normal', 1, %s, true, 'ok', %s)""",
                    (vid, seq, '{"magnitude_mm": "test-only"}', OTHER),
                )
            return uuid.UUID(str(vid))

    def walk(self, vid: uuid.UUID, events: list[Event]) -> None:
        with app_conn(self.url) as c, c.transaction():
            for e in events:
                transition(c, vid, e)

    def approve(self, vid: uuid.UUID) -> None:
        """The DATA-05 record FN-REV-04 writes (its gates are that task's)."""
        with psycopg.connect(self.url) as c:
            c.execute(
                """INSERT INTO governance.approval (design_version_id, geometry_sha, params_sha,
                       scan_sha, measurement_set_id, prescription_sha, checklist_version,
                       checklist_answers, config_version, self_approval, statement_text,
                       approver_id, approver_role)
                   VALUES (%s, %s, %s, %s, %s, %s, 1, '{}', 1, false, 'test statement', %s,
                           'technician')""",
                (vid, sha("geom"), sha("params"), sha("scan"), self.measurements, sha("rx"), USER),
            )


@pytest.fixture
def seed(empty_db_url: str, seed_user: Callable[..., None]) -> Seed:
    from jude_api.db.migrate import upgrade

    upgrade(empty_db_url)
    seed_user(empty_db_url, USER, OTHER)
    return Seed(empty_db_url)


def rows(url: str, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as c:
        return c.execute(sql, params).fetchall()


def status_of(url: str, vid: uuid.UUID) -> str:
    return str(rows(url, "SELECT status FROM geometry.design_version WHERE id = %s", (vid,))[0][0])


def edit(url: str, vid: uuid.UUID) -> uuid.UUID:
    with app_conn(url) as c, c.transaction():
        return draft_for_edit(c, vid, USER)


# --- completion criterion ---------------------------------------------------------------------


def test_completion_criterion_edit_after_approval_gives_an_unapproved_new_version(
    seed: Seed,
) -> None:
    v1 = seed.version()
    seed.walk(v1, PATHS[Status.APPROVED])
    seed.approve(v1)
    approval_before = rows(seed.url, "SELECT * FROM governance.approval")

    v2 = edit(seed.url, v1)

    assert v2 != v1
    number, parent, status, geometry = rows(
        seed.url,
        "SELECT number, parent_id, status, geometry_sha FROM geometry.design_version WHERE id = %s",
        (v2,),
    )[0]
    assert (number, parent, status, geometry) == (2, v1, "draft", sha("geom"))
    assert status_of(seed.url, v1) == "approved"  # the old version keeps its status
    assert rows(seed.url, "SELECT * FROM governance.approval") == approval_before  # unchanged
    assert rows(seed.url, "SELECT count(*) FROM governance.approval WHERE design_version_id = %s",
                (v2,)) == [(0,)]  # approval never carries over  # fmt: skip
    # the op log continues in the draft, each op keeping its author (FR-093 self-approval)
    ops = (
        "SELECT seq, type, created_by FROM geometry.operation"
        " WHERE design_version_id = %s ORDER BY seq"
    )
    assert rows(seed.url, ops, (v2,)) == rows(seed.url, ops, (v1,)) == [
        (1, "offset.uniform_normal", OTHER), (2, "offset.uniform_normal", OTHER),
    ]  # fmt: skip
    assert edit(seed.url, v1) == v2  # further edits continue in the same draft
    assert edit(seed.url, v2) == v2  # a draft is edited in place
    # the new draft starts its own life: it must be saved, reviewed and approved again
    with app_conn(seed.url) as c, c.transaction(), pytest.raises(ApiError) as exc:
        transition(c, v2, Event.APPROVE)
    assert exc.value.code == "ILLEGAL_STATE"


# --- service ----------------------------------------------------------------------------------


def test_lifecycle_through_the_service(seed: Seed) -> None:
    v = seed.version()
    for event, expected in [
        (Event.SAVE, "saved"), (Event.REVIEW_FAILED, "reviewed_fail"),
        (Event.REVIEW_PASSED, "reviewed_pass"), (Event.APPROVE, "approved"),
        (Event.EXPORT, "exported"), (Event.EXPORT, "exported"), (Event.SUPERSEDE, "superseded"),
    ]:  # fmt: skip
        seed.walk(v, [event])
        assert status_of(seed.url, v) == expected


@pytest.mark.parametrize(
    ("state", "event"),
    [(Status.DRAFT, Event.APPROVE), (Status.REVIEWED_FAIL, Event.APPROVE),
     (Status.SAVED, Event.EXPORT), (Status.APPROVED, Event.REJECT),
     (Status.APPROVED, Event.REVIEW_PASSED), (Status.SUPERSEDED, Event.SAVE),
     (Status.REJECTED, Event.APPROVE), (Status.SAVED, Event.SAVE)],
)  # fmt: skip
def test_illegal_transition_is_409_and_changes_nothing(
    seed: Seed, state: Status, event: Event
) -> None:
    v = seed.version()
    seed.walk(v, PATHS[state])
    with app_conn(seed.url) as c, pytest.raises(ApiError) as exc, c.transaction():
        transition(c, v, event)
    assert exc.value.code == "ILLEGAL_STATE"
    assert status_of(seed.url, v) == state.value


def test_unknown_version_is_not_found(seed: Seed) -> None:
    with app_conn(seed.url) as c, pytest.raises(ApiError) as exc:
        transition(c, uuid.uuid4(), Event.SAVE)
    assert exc.value.code == "NOT_FOUND"


def test_a_superseded_version_is_not_the_parent_of_new_work(seed: Seed) -> None:
    v = seed.version()
    seed.walk(v, PATHS[Status.APPROVED] + [Event.SUPERSEDE])
    with app_conn(seed.url) as c, pytest.raises(ApiError) as exc, c.transaction():
        draft_for_edit(c, v, USER)
    assert exc.value.code == "DEPENDENCY_SUPERSEDED"


def test_one_open_draft_per_design(seed: Seed) -> None:
    v1 = seed.version()
    seed.walk(v1, PATHS[Status.REJECTED])
    v2 = edit(seed.url, v1)
    seed.walk(v2, [Event.SAVE])
    v3 = edit(seed.url, v2)  # draft 3 from version 2
    assert v3 not in (v1, v2)
    with app_conn(seed.url) as c, pytest.raises(ApiError) as exc, c.transaction():
        draft_for_edit(c, v1, USER)  # another parent while draft 3 is open
    assert exc.value.code == "ILLEGAL_STATE"
    numbers = "SELECT number, status FROM geometry.design_version ORDER BY number"
    assert rows(seed.url, numbers) == [(1, "rejected"), (2, "saved"), (3, "draft")]


def test_concurrent_edits_of_one_version_share_one_draft(seed: Seed) -> None:
    v1 = seed.version()
    seed.walk(v1, PATHS[Status.APPROVED])
    barrier, drafts, failures = threading.Barrier(6), [], []

    def run() -> None:
        try:
            with app_conn(seed.url) as c:
                barrier.wait()
                with c.transaction():
                    drafts.append(draft_for_edit(c, v1, USER))
        except Exception as exc:
            failures.append(exc)

    threads = [threading.Thread(target=run) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert failures == [] and len(set(drafts)) == 1
    count = "SELECT count(*) FROM geometry.design_version WHERE status = 'draft'"
    assert rows(seed.url, count) == [(1,)]


# --- database backstop (migration 0007) -------------------------------------------------------


def test_database_guard_matches_the_table_for_every_pair(seed: Seed) -> None:
    allowed = status_changes()
    checked = 0
    for old, new in itertools.permutations(Status, 2):
        v = seed.version(ops=0)
        seed.walk(v, PATHS[old])
        with app_conn(seed.url) as c:
            try:
                with c.transaction():
                    c.execute("UPDATE geometry.design_version SET status = %s WHERE id = %s",
                              (new.value, v))  # fmt: skip
                accepted = True
            except errors.RaiseException as exc:
                assert "ILLEGAL_STATE" in str(exc)
                accepted = False
        assert accepted == ((old.value, new.value) in allowed), (old, new)
        checked += 1
    assert checked == 56


def test_saved_version_is_immutable_except_status(seed: Seed) -> None:
    v = seed.version()
    with app_conn(seed.url) as c:
        c.execute("UPDATE geometry.design_version SET geometry_sha = %s WHERE id = %s",
                  (sha("draft edit"), v))  # a draft may change  # fmt: skip
        c.commit()
    seed.walk(v, [Event.SAVE])
    for column, value in [("geometry_sha", sha("x")), ("params_sha", sha("y")),
                          ("template_ref", "t"), ("regen_failed", True)]:  # fmt: skip
        with app_conn(seed.url) as c, pytest.raises(errors.RaiseException, match="INV-03"):
            c.execute(f"UPDATE geometry.design_version SET {column} = %s WHERE id = %s",  # noqa: S608
                      (value, v))  # fmt: skip


def test_versions_are_born_as_drafts_and_saved_means_hashed(seed: Seed) -> None:
    v = seed.version()
    design = rows(seed.url, "SELECT design_id FROM geometry.design_version WHERE id = %s", (v,))
    insert = """INSERT INTO geometry.design_version (design_id, number, status, scan_sha,
                    frame_id, config_version, created_by) VALUES (%s, 9, %s, %s, %s, 1, %s)"""
    with app_conn(seed.url) as c, pytest.raises(errors.RaiseException, match="created as draft"):
        c.execute(insert, (design[0][0], "approved", sha("scan"), seed.frame, USER))
    with app_conn(seed.url) as c, pytest.raises(errors.UniqueViolation):
        c.execute(insert, (design[0][0], "draft", sha("scan"), seed.frame, USER))  # 2nd draft
    # an unknown status: the guard (BEFORE trigger) refuses it before the CHECK would
    with app_conn(seed.url) as c, pytest.raises(errors.RaiseException, match="ILLEGAL_STATE"):
        c.execute("UPDATE geometry.design_version SET status = 'approvedd' WHERE id = %s", (v,))
    bare = seed.version()
    with app_conn(seed.url) as c:
        c.execute("UPDATE geometry.design_version SET geometry_sha = NULL WHERE id = %s", (bare,))
        c.commit()
        with pytest.raises(errors.CheckViolation):
            c.execute("UPDATE geometry.design_version SET status = 'saved' WHERE id = %s",
                      (bare,))  # fmt: skip


def test_concurrent_edits_of_two_versions_of_one_design(seed: Seed) -> None:
    v1 = seed.version()
    seed.walk(v1, PATHS[Status.REJECTED])
    v2 = edit(seed.url, v1)
    seed.walk(v2, [Event.SAVE])  # versions 1 and 2 are both non-drafts now
    barrier, outcomes = threading.Barrier(2), []

    def run(source: uuid.UUID) -> None:
        with app_conn(seed.url) as c:
            barrier.wait()
            try:
                with c.transaction():
                    draft_for_edit(c, source, USER)
                outcomes.append("draft")
            except ApiError as exc:
                outcomes.append(exc.code)  # a clean 409, not a unique-index error

    threads = [threading.Thread(target=run, args=(s,)) for s in (v1, v2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert sorted(outcomes) == ["ILLEGAL_STATE", "draft"]
