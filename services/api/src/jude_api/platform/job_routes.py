"""FN-JOB-03 Report job status (TSK-JOB-03-A; TD-15, IF-02).

``GET /api/v1/jobs/{job_id}`` lets the UI follow a long operation by polling.

- Visible to the requester who queued the job, or to anyone who may access its case
  (``case_access``, TSK-IAM-04-A). A job the requester may not see answers exactly like an
  unknown one, 404 NOT_FOUND, so job ids cannot be probed.
- Every call reads the committed row (no caching, ``Cache-Control: no-store``): a status
  change made by the worker is visible on the next poll (completion criterion).
- The result is the kernel summary from the job-result/1 envelope (status, reason code,
  report, output names), never geometry. A failed job carries its catalogue code and the
  Russian message (NFR-05) and the step that resolves the code (FN-UIX-03), so the view can
  link to it when the job ends.
"""

from typing import Annotated, Any
import uuid

from fastapi import APIRouter, Depends, Response
import psycopg

from jude_api.domain.uix.steps import target_step
from jude_api.platform.authz import ActionCheck
from jude_api.platform.deps import CaseAccess, CaseAccessCheck, Db, Requester
from jude_api.platform.errors import ApiError, catalogue, messages_ru
from jude_api.platform.schemas import ERROR_RESPONSES, ErrorResponse, JobStatusResponse

JOBS_PREFIX = "/api/v1/jobs"
SUMMARY_KEYS = ("op_type", "op_version", "status", "reason_code", "output_names", "report")


def _summary(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict) or not all(k in result for k in SUMMARY_KEYS):
        return None
    return {k: result[k] for k in SUMMARY_KEYS}


def job_status(
    conn: psycopg.Connection[Any], job_id: uuid.UUID, who: Requester, may_access: CaseAccess
) -> dict[str, Any] | None:
    """The status document, or None when the job is unknown or not visible to ``who``."""
    row = conn.execute(
        """
        SELECT id, type, status, attempts, payload, result, error_code, case_id, requested_by,
               created_at, finished_at
          FROM ops.job WHERE id = %s
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    jid, jtype, status, attempts, payload, result, error_code, case_id, owner, created, finished = (
        row
    )
    if owner != who.user_id and not (case_id is not None and may_access(who, case_id)):
        return None
    entry = catalogue().get(error_code) if error_code else None
    progress = result.get("progress") if isinstance(result, dict) else None
    return {
        "job_id": jid,
        "type": jtype,
        "status": status,
        "attempts": attempts,
        "progress": progress if isinstance(progress, (int, float)) else None,
        "result": _summary(result),
        "error_code": error_code,
        "message_ru": messages_ru()[entry["message_key"]] if entry else None,
        "step": target_step(error_code) if entry else None,
        "correlation_id": (payload or {}).get("correlation_id"),
        "created_at": created,
        "finished_at": finished,
    }


router = APIRouter(prefix=JOBS_PREFIX, responses=ERROR_RESPONSES)


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    responses={404: {"model": ErrorResponse, "description": "Unknown job, or not visible"}},
)
def get_job(
    job_id: uuid.UUID,
    who: Annotated[Requester, Depends(ActionCheck("FN-JOB-03"))],  # session checked first
    may_access: CaseAccessCheck,
    conn: Db,
    response: Response,
) -> dict[str, Any]:
    status = job_status(conn, job_id, who, may_access)
    conn.commit()
    if status is None:
        raise ApiError("NOT_FOUND")
    response.headers["Cache-Control"] = "no-store"
    return status
