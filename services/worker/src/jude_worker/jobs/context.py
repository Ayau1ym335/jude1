"""Correlation through a job: payload -> worker logs -> job result envelope (XC-FND-11).

The kernel stays pure and never sees the ID (IF-03); the worker binds it while the job runs
and writes it next to the kernel's OpResult in the job result (DS-17 ``result``), so a UI
action can be followed to the kernel report that answered it.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import logging
from typing import Any

from jude_kernel.core import OpResult
from jude_platform import correlation

log = logging.getLogger("jude_worker.job")
RESULT_SCHEMA = "job-result/1"


@contextmanager
def job_context(job_id: str, job_type: str, payload: Mapping[str, object]) -> Iterator[str]:
    """Bind the payload's correlation ID and log the job lifecycle (no payload content)."""
    cid = correlation.extract(payload)
    with correlation.bound(cid):
        log.info("job.started", extra={"job_id": job_id, "job_type": job_type})
        try:
            yield cid
        except Exception:
            log.exception("job.failed", extra={"job_id": job_id, "job_type": job_type})
            raise
        log.info("job.finished", extra={"job_id": job_id, "job_type": job_type})


def result_envelope(
    result: OpResult, correlation_id: str, timings_ms: Mapping[str, float] | None = None
) -> dict[str, Any]:
    """Job result for ops.job.result: the kernel report plus provenance and correlation.

    Output geometry is referenced by blob SHA in TSK-JOB-04 (completion handler), not here.
    """
    return {
        "schema": RESULT_SCHEMA,
        "correlation_id": correlation_id,
        "status": result.status.value,
        "op_type": result.op_type,
        "op_version": result.op_version,
        "reason_code": result.reason_code,
        "kernel_version": result.kernel_version,
        "image_digest": result.image_digest,
        "lib_versions": dict(result.lib_versions),
        "report": dict(result.report),
        "output_names": sorted(result.outputs),
        "timings_ms": dict(timings_ms or {}),
    }
