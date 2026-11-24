"""FN-REV-06 service: apply transitions and derive drafts (TSK-REV-06-A; FR-091, FR-056, SAF-08).

Both functions run in the caller's transaction and lock the version row (FOR UPDATE), so the
check and the write cannot interleave with another request.

- ``transition(conn, version_id, event)``: moves the version according to ``states``. The
  caller's function writes its own audit event (design.version_saved, design.reviewed,
  design.approved, ...); the state machine adds none.
- ``draft_for_edit(conn, version_id)``: the version an edit applies to (FR-091). A draft is
  edited in place. Any other version gets draft n+1, with its parent n, a copy of n's
  operation log (each op keeps its author and time, as needed for the self-approval check
  FR-093) and n's hashes. Version n, its status and its approval stay as they are: the new
  draft has no approval, because an approval belongs to (version id, geometry_sha). If a draft
  derived from n already exists, the same draft is returned. If the design's open draft has
  another parent, the answer is ILLEGAL_STATE, because a design has a single open draft.
"""

from typing import Any
import uuid

import psycopg

from jude_api.domain.rev.states import Event, Status, editable_in_place, next_status
from jude_api.platform.errors import ApiError


def _locked(conn: psycopg.Connection[Any], version_id: uuid.UUID) -> tuple[Any, ...]:
    row = conn.execute(
        "SELECT status, design_id FROM geometry.design_version WHERE id = %s FOR UPDATE",
        (version_id,),
    ).fetchone()
    if row is None:
        raise ApiError("NOT_FOUND")
    return tuple(row)


def transition(conn: psycopg.Connection[Any], version_id: uuid.UUID, event: Event) -> Status:
    current = Status(_locked(conn, version_id)[0])
    new = next_status(current, event)
    if new is not current:
        conn.execute(
            "UPDATE geometry.design_version SET status = %s WHERE id = %s", (new.value, version_id)
        )
    return new


def draft_for_edit(
    conn: psycopg.Connection[Any], version_id: uuid.UUID, actor_id: uuid.UUID
) -> uuid.UUID:
    status, design_id = _locked(conn, version_id)
    status = Status(status)
    if editable_in_place(status):
        return version_id
    if status is Status.SUPERSEDED:
        raise ApiError("DEPENDENCY_SUPERSEDED")
    # Serialise draft creation per design: the open-draft check below sees no row to lock when
    # no draft exists, so two edits of different versions would otherwise race for number n+1.
    conn.execute("SELECT 1 FROM geometry.design WHERE id = %s FOR UPDATE", (design_id,))
    open_draft = conn.execute(
        "SELECT id, parent_id FROM geometry.design_version"
        " WHERE design_id = %s AND status = 'draft' FOR UPDATE",
        (design_id,),
    ).fetchone()
    if open_draft is not None:
        if open_draft[1] == version_id:
            return uuid.UUID(str(open_draft[0]))  # the edit continues in the same draft
        raise ApiError("ILLEGAL_STATE")
    row = conn.execute(
        """
        INSERT INTO geometry.design_version
               (design_id, number, parent_id, status, scan_sha, frame_id, config_version,
                template_ref, params_sha, geometry_sha, kernel_version, kernel_image_digest,
                created_by)
        SELECT design_id,
               (SELECT max(number) + 1 FROM geometry.design_version WHERE design_id = v.design_id),
               id, 'draft', scan_sha, frame_id, config_version, template_ref, params_sha,
               geometry_sha, kernel_version, kernel_image_digest, %s
          FROM geometry.design_version v WHERE id = %s
        RETURNING id
        """,
        (actor_id, version_id),
    ).fetchone()
    if row is None:  # unreachable: the source row is locked above
        raise ApiError("NOT_FOUND")
    draft_id = uuid.UUID(str(row[0]))
    conn.execute(
        """
        INSERT INTO geometry.operation
               (design_version_id, seq, type, op_version, params, enabled, status,
                reason_code, report, created_by, created_at)
        SELECT %s, seq, type, op_version, params, enabled, status, reason_code, report,
               created_by, created_at
          FROM geometry.operation WHERE design_version_id = %s
        """,
        (draft_id, version_id),
    )
    return draft_id
