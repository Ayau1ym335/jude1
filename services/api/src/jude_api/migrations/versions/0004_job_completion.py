"""Job completion bookkeeping (FN-JOB-04) and column-level worker grants.

Revision ID: 0004_job_completion
Revises: 0003_iam_accounts
Create Date: 2026-11-23
Task: TSK-JOB-04-J

- ops.job.completion ('applied' | 'superseded_result') and completed_at: set by the completion
  handler in the API (C3) in the same transaction as the domain change and its audit event,
  so an outcome is applied exactly once. completion_attempts counts failed handler runs; after
  three the job is skipped (and logged) instead of blocking the queue.
- worker_rw: UPDATE only on the columns the worker owns; it can neither mark a job completed
  nor touch the completion columns (the worker never writes domain state or audit, FN-JOB-04).
"""

from alembic import op

revision = "0004_job_completion"
down_revision = "0003_iam_accounts"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    ALTER TABLE ops.job
      ADD COLUMN completion text NULL CHECK (completion IN ('applied', 'superseded_result')),
      ADD COLUMN completed_at timestamptz NULL,
      ADD COLUMN completion_attempts integer NOT NULL DEFAULT 0 CHECK (completion_attempts >= 0),
      ADD CONSTRAINT job_completion_pair CHECK ((completion IS NULL) = (completed_at IS NULL)),
      ADD CONSTRAINT job_completion_terminal
        CHECK (completion IS NULL OR status IN ('succeeded', 'failed'))
    """,
    "CREATE INDEX job_completion_queue ON ops.job (finished_at) "
    "WHERE status IN ('succeeded', 'failed') AND completed_at IS NULL",
    "REVOKE UPDATE ON ops.job FROM worker_rw",
    "GRANT UPDATE (status, attempts, worker_id, lease_until, heartbeat_at, result, error_code,"
    " finished_at) ON ops.job TO worker_rw",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations: write a new migration instead")
