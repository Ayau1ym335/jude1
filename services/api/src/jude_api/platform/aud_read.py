"""FN-AUD-02 Log read access (TSK-AUD-02-A; SEC-15, FR-164, IF-08).

Every view or download of an infant data object leaves one audit event. The event is
committed before the body is sent, so there is no unlogged read. Download endpoints (scan
blobs, display meshes, exports, reports, the audit CSV, prescription files) return through
``logged_download`` (or call ``record_read`` before streaming):

1. it is called after authorisation, with the object's case and id;
2. it appends the read event through FN-AUD-01 (the hash-chained audit log), carrying user,
   role, UTC time, case id, object type, object id and UI session;
3. it commits in its own transaction: a read transaction the request may have opened is
   committed first (it only read), so the event never rides along with anything else and is
   durable before a byte of the body leaves;
4. if the audit write fails for any reason, it answers 503 AUDIT_UNAVAILABLE and returns no
   data.

| object read           | event               |
|-----------------------|---------------------|
| scan blob             | blob.read           |
| display mesh          | blob.read           |
| export (STL/manifest) | export.downloaded   |
| report                | report.downloaded   |
| audit CSV             | audit.exported      |
| prescription file     | prescription.read   |
"""

from dataclasses import dataclass
from enum import StrEnum
import logging
from types import MappingProxyType
from typing import Any, Final

from fastapi import Response
import psycopg
from psycopg import pq

from jude_api.platform import aud
from jude_api.platform.errors import ApiError
from jude_api.platform.iam import Requester

log = logging.getLogger("jude_api.aud_read")


class ReadKind(StrEnum):
    SCAN_BLOB = "scan_blob"
    DISPLAY_MESH = "display_mesh"
    EXPORT = "export"
    REPORT = "report"
    AUDIT_CSV = "audit_csv"
    PRESCRIPTION = "prescription"


@dataclass(frozen=True)
class ReadEvent:
    event_type: str
    object_type: str


READ_EVENTS: Final = MappingProxyType({
    ReadKind.SCAN_BLOB: ReadEvent("blob.read", "scan"),
    ReadKind.DISPLAY_MESH: ReadEvent("blob.read", "display_mesh"),
    ReadKind.EXPORT: ReadEvent("export.downloaded", "export"),
    ReadKind.REPORT: ReadEvent("report.downloaded", "report"),
    ReadKind.AUDIT_CSV: ReadEvent("audit.exported", "audit_csv"),
    ReadKind.PRESCRIPTION: ReadEvent("prescription.read", "prescription"),
})  # fmt: skip


def record_read(
    conn: psycopg.Connection[Any],
    who: Requester,
    kind: ReadKind,
    *,
    case_id: str | None,
    object_id: str,
) -> int:
    """Append and commit the read event; its seq. AUDIT_UNAVAILABLE if that is not possible."""
    spec = READ_EVENTS[kind]
    event = aud.AuditEvent(
        spec.event_type, who.user_id, who.role, object_type=spec.object_type,
        object_id=object_id, case_id=case_id, ui_session_id=who.ui_session_id,
    )  # fmt: skip
    try:
        if conn.info.transaction_status == pq.TransactionStatus.INTRANS:
            conn.commit()  # the request's own reads: the event gets a transaction of its own
        with conn.transaction():
            return aud.append(conn, event)
    except Exception:
        log.exception("audit.read_not_recorded", extra={"event_type": spec.event_type})
        raise ApiError("AUDIT_UNAVAILABLE") from None


def logged_download(
    conn: psycopg.Connection[Any],
    who: Requester,
    kind: ReadKind,
    *,
    case_id: str | None,
    object_id: str,
    content: bytes,
    media_type: str,
    filename: str,
) -> Response:
    """FN-AUD-02 for a whole-body download: the event is committed, then the bytes are sent."""
    record_read(conn, who, kind, case_id=case_id, object_id=object_id)
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
