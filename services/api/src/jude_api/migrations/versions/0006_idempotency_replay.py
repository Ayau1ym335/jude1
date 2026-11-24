"""Idempotency replay record: request fingerprint and exact response bytes (FN-API-01, NFR-07).

Revision ID: 0006_idempotency_replay
Revises: 0005_user_references
Create Date: 2026-11-24
Task: TSK-API-01-A

ops.idempotency_key (baseline) stores (user, key, status, body hash, body). Two columns are
added:

- request_sha: SHA-256 of method, path and request body. A key reused for a different request
  is refused (IDEMPOTENCY_KEY_REUSED) instead of replaying an unrelated response.
- body_bytes: the exact response bytes. A replay returns a body identical to the original
  (completion criterion). jsonb cannot do that, because it reorders keys. body_sha is the
  SHA-256 of these bytes, checked by the database. ``body`` keeps the parsed JSON for queries.

The table holds no rows before this task (no route wrote it), so NOT NULL needs no default.
"""

from alembic import op

revision = "0006_idempotency_replay"
down_revision = "0005_user_references"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    ALTER TABLE ops.idempotency_key
      ADD COLUMN request_sha char(64) NOT NULL CHECK (request_sha ~ '^[0-9a-f]{64}$'),
      ADD COLUMN body_bytes bytea NOT NULL,
      ADD CONSTRAINT idempotency_body_sha CHECK (body_sha = encode(sha256(body_bytes), 'hex'))
    """,
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations: write a new migration instead")
