"""Foreign keys from the *_by / user_id columns to governance."user" (FN-IAM-05, SEC-01).

Revision ID: 0005_user_references
Revises: 0004_job_completion
Create Date: 2026-11-24
Task: TSK-IAM-05-B

Every recorded actor is a named account (SEC-01). Accounts are never deleted, only
deactivated (SEC-19). So these references never dangle, and app_rw has no DELETE on the table.

audit.audit_event.user_id gets **no** foreign key. The audit record is the evidence log. Its
integrity rests on the hash chain alone, not on another table. It also records actors that are
not accounts: user_id NULL, for example the first-admin bootstrap or the system itself.
"""

from alembic import op

revision = "0005_user_references"
down_revision = "0004_job_completion"
branch_labels = None
depends_on = None

REFERENCES = [
    ('clinical."case"', "archived_by"),
    ('clinical."case"', "created_by"),
    ("clinical.consent_ref", "created_by"),
    ("clinical.prescription", "attached_by"),
    ("clinical.scan_metadata", "updated_by"),
    ("geometry.design", "created_by"),
    ("geometry.design_version", "created_by"),
    ("geometry.frame", "confirmed_by"),
    ("geometry.frame", "created_by"),
    ("geometry.landmark", "placed_by"),
    ("geometry.landmark_history", "created_by"),
    ("geometry.landmark_set", "created_by"),
    ("geometry.measurement_set", "created_by"),
    ("geometry.operation", "created_by"),
    ("geometry.scan", "uploaded_by"),
    ("governance.config_version", "controlled_last_changed_by"),
    ("governance.config_version", "published_by"),
    ("governance.export", "created_by"),
    ("governance.measurement_definition", "created_by"),
    ('governance."user"', "created_by"),
    ("ops.idempotency_key", "user_id"),
    ("ops.job", "requested_by"),
]


def _name(table: str, column: str) -> str:
    return f"{table.split('.')[1].strip(chr(34))}_{column}_user_fk"


STATEMENTS = [
    f"ALTER TABLE {table} ADD CONSTRAINT {_name(table, column)} FOREIGN KEY ({column})"
    ' REFERENCES governance."user"(id)'
    for table, column in REFERENCES
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations: write a new migration instead")
