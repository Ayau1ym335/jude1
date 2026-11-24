"""UT-FN-REV-06: design version transition table (no database)."""

import importlib.util
import itertools
from pathlib import Path
from types import ModuleType

import pytest

from jude_api.domain.rev.states import (
    TRANSITIONS,
    Event,
    Status,
    editable_in_place,
    next_status,
    status_changes,
)
from jude_api.platform.errors import ApiError

S, E = Status, Event


def _migration_0007() -> ModuleType:
    import jude_api

    versions = Path(jude_api.__file__).parent / "migrations" / "versions"
    path = versions / "0007_design_version_states.py"
    spec = importlib.util.spec_from_file_location("m0007", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The FS chain draft -> saved -> reviewed_* -> approved|rejected -> exported, any -> superseded.
EXPECTED = {
    (S.DRAFT, E.SAVE): S.SAVED,
    (S.SAVED, E.REVIEW_PASSED): S.REVIEWED_PASS,
    (S.SAVED, E.REVIEW_FAILED): S.REVIEWED_FAIL,
    (S.REVIEWED_PASS, E.REVIEW_PASSED): S.REVIEWED_PASS,
    (S.REVIEWED_PASS, E.REVIEW_FAILED): S.REVIEWED_FAIL,
    (S.REVIEWED_FAIL, E.REVIEW_PASSED): S.REVIEWED_PASS,
    (S.REVIEWED_FAIL, E.REVIEW_FAILED): S.REVIEWED_FAIL,
    (S.REVIEWED_PASS, E.APPROVE): S.APPROVED,
    (S.SAVED, E.REJECT): S.REJECTED,
    (S.REVIEWED_PASS, E.REJECT): S.REJECTED,
    (S.REVIEWED_FAIL, E.REJECT): S.REJECTED,
    (S.APPROVED, E.EXPORT): S.EXPORTED,
    (S.EXPORTED, E.EXPORT): S.EXPORTED,
    **{(s, E.SUPERSEDE): S.SUPERSEDED for s in S},
}


def test_the_table_is_exactly_the_specified_one() -> None:
    assert dict(TRANSITIONS) == EXPECTED


@pytest.mark.parametrize(("status", "event"), list(itertools.product(Status, Event)))
def test_every_other_pair_is_illegal_state(status: Status, event: Event) -> None:
    if (status, event) in EXPECTED:
        assert next_status(status, event) is EXPECTED[(status, event)]
        return
    with pytest.raises(ApiError) as exc:
        next_status(status, event)
    assert exc.value.code == "ILLEGAL_STATE"


def test_key_safety_rules() -> None:
    # approval only after a passed review; never from a failed one or a draft
    assert {s for (s, e) in TRANSITIONS if e is E.APPROVE} == {S.REVIEWED_PASS}
    # export only of an approved (or already exported) version
    assert {s for (s, e) in TRANSITIONS if e is E.EXPORT} == {S.APPROVED, S.EXPORTED}
    # nothing leaves superseded except superseding again; nothing goes back to draft
    assert {b for (a, _), b in TRANSITIONS.items() if a is S.SUPERSEDED} == {S.SUPERSEDED}
    assert S.DRAFT not in TRANSITIONS.values()
    # an approved version is never re-reviewed or rejected (edits create a new version)
    assert {e for (s, e) in TRANSITIONS if s is S.APPROVED} == {E.EXPORT, E.SUPERSEDE}


def test_only_drafts_are_edited_in_place() -> None:
    assert [s for s in Status if editable_in_place(s)] == [S.DRAFT]


def test_database_guard_allows_exactly_the_same_changes() -> None:
    m0007 = _migration_0007()
    assert set(m0007.ALLOWED) == status_changes()
    assert tuple(m0007.STATUSES) == tuple(s.value for s in Status)
