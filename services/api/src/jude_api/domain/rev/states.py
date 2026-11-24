"""FN-REV-06 Design version state machine: the transition table (TSK-REV-06-A; FR-091, FR-056,
SAF-08, ADR-008).

Single authority for version status changes. Every service that moves a version (save
FN-DES-04, review FN-REV-01, approve FN-REV-04, reject FN-REV-05, export FN-EXP-02, supersede
FN-ANA-05) asks ``next_status``; anything else is 409 ILLEGAL_STATE. Migration
``0007_design_version_states`` enforces the same pairs in the database.

    draft -> saved -> reviewed_pass | reviewed_fail -> approved | rejected -> exported
    any -> superseded

The FS chain leaves some edges open. The table settles them from the preconditions of the
functions that cause each transition (engineering reading, 2026-11-24):

- review (FN-REV-01, precondition "version saved", meaning not a draft): from saved and from a
  previous review result. A re-review replaces the result; it is never possible after approval,
  rejection or export.
- approve (FN-REV-04, precondition "version reviewed_pass"): from reviewed_pass only.
- reject (FN-REV-05, precondition "version saved or reviewed"): from saved, reviewed_pass and
  reviewed_fail. An approved version is not rejected; an edit creates a new version instead.
- export (FN-EXP-02): approved -> exported; a further export of an exported version keeps it
  exported.
- supersede (FN-ANA-05, "any -> superseded"): from every state; superseded is final and
  superseding again changes nothing.

Edits (FR-091) are not transitions. An edit of a draft changes the draft. An edit of any other
version creates draft n+1 with parent n (``versions.draft_for_edit``), and the old version
keeps its status and approval. Approval never carries over to a new version. A superseded
version cannot be the parent of a new draft (SAF-08: outdated anatomy must not come back as
fresh work): 409 DEPENDENCY_SUPERSEDED.
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from jude_api.platform.errors import ApiError


class Status(StrEnum):
    DRAFT = "draft"
    SAVED = "saved"
    REVIEWED_PASS = "reviewed_pass"  # noqa: S105 - a status name, not a password
    REVIEWED_FAIL = "reviewed_fail"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPORTED = "exported"
    SUPERSEDED = "superseded"


class Event(StrEnum):
    SAVE = "save"  # FN-DES-04
    REVIEW_PASSED = "review_passed"  # FN-REV-01
    REVIEW_FAILED = "review_failed"  # FN-REV-01
    APPROVE = "approve"  # FN-REV-04
    REJECT = "reject"  # FN-REV-05
    EXPORT = "export"  # FN-EXP-02
    SUPERSEDE = "supersede"  # FN-ANA-05


_REVIEWABLE = (Status.SAVED, Status.REVIEWED_PASS, Status.REVIEWED_FAIL)

TRANSITIONS: Mapping[tuple[Status, Event], Status] = MappingProxyType({
    (Status.DRAFT, Event.SAVE): Status.SAVED,
    **{(s, Event.REVIEW_PASSED): Status.REVIEWED_PASS for s in _REVIEWABLE},
    **{(s, Event.REVIEW_FAILED): Status.REVIEWED_FAIL for s in _REVIEWABLE},
    **{(s, Event.REJECT): Status.REJECTED for s in _REVIEWABLE},
    (Status.REVIEWED_PASS, Event.APPROVE): Status.APPROVED,
    (Status.APPROVED, Event.EXPORT): Status.EXPORTED,
    (Status.EXPORTED, Event.EXPORT): Status.EXPORTED,
    **{(s, Event.SUPERSEDE): Status.SUPERSEDED for s in Status},
})  # fmt: skip


def next_status(current: Status, event: Event) -> Status:
    """The status after ``event``; 409 ILLEGAL_STATE if the event is not allowed now."""
    try:
        return TRANSITIONS[(current, event)]
    except KeyError:
        raise ApiError("ILLEGAL_STATE") from None


def editable_in_place(status: Status) -> bool:
    """Only a draft is edited in place; any other version is edited through a new draft."""
    return status is Status.DRAFT


def status_changes() -> frozenset[tuple[str, str]]:
    """(from, to) pairs that change the status: what the database guard must allow."""
    return frozenset((a.value, b.value) for (a, _), b in TRANSITIONS.items() if a is not b)
