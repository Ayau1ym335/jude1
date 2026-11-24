"""Design version status set, transitions and immutability in the database (FN-REV-06).

Revision ID: 0007_design_version_states
Revises: 0006_idempotency_replay
Create Date: 2026-11-24
Task: TSK-REV-06-A

``jude_api.domain.rev.states`` is the single authority for status transitions (FN-REV-06,
ADR-008). This migration is the backstop, so a write that bypasses the service cannot break
the rules:

- **status**: a CHECK over the eight states of FN-REV-06 (07 §8.1). The baseline left this
  column open for this task.
- **birth**: a version is inserted as ``draft`` only.
- **transitions**: a status change must be one of ``ALLOWED`` below, the same pairs as the
  Python table (a test compares them).
- **INV-03 / FR-056**: once a version leaves ``draft``, every column except ``status`` is
  frozen.
- **saved means hashed**: outside ``draft`` and ``superseded`` (a draft can be superseded
  before its first save), ``params_sha`` and ``geometry_sha`` are present.
- **one open draft per design** (partial unique index). An edit of a non-draft creates draft
  n+1 (FR-091), and there is only one place to edit.

Violations raise SQLSTATE P0001 with the message prefix ``ILLEGAL_STATE``.
"""

from alembic import op

revision = "0007_design_version_states"
down_revision = "0006_idempotency_replay"
branch_labels = None
depends_on = None

STATUSES = (
    "draft", "saved", "reviewed_pass", "reviewed_fail", "approved", "rejected", "exported",
    "superseded",
)  # fmt: skip

# (from, to) pairs with a status change; must equal states.status_changes().
ALLOWED = (
    ("draft", "saved"),
    ("saved", "reviewed_pass"), ("saved", "reviewed_fail"),
    ("reviewed_pass", "reviewed_fail"), ("reviewed_fail", "reviewed_pass"),
    ("reviewed_pass", "approved"),
    ("saved", "rejected"), ("reviewed_pass", "rejected"), ("reviewed_fail", "rejected"),
    ("approved", "exported"),
    *((s, "superseded") for s in STATUSES if s != "superseded"),
)  # fmt: skip

FROZEN = (
    "id", "design_id", "number", "parent_id", "scan_sha", "frame_id", "config_version",
    "template_ref", "params_sha", "geometry_sha", "kernel_version", "kernel_image_digest",
    "regen_failed", "created_by", "created_at",
)  # fmt: skip


def _row(prefix: str) -> str:
    return "(" + ", ".join(f"{prefix}.{c}" for c in FROZEN) + ")"


_PAIRS = ", ".join(f"('{a}', '{b}')" for a, b in ALLOWED)
_STATUS_LIST = ", ".join(f"'{s}'" for s in STATUSES)

STATEMENTS = [
    f"""
    ALTER TABLE geometry.design_version
      ADD CONSTRAINT design_version_status CHECK (status IN ({_STATUS_LIST})),
      ADD CONSTRAINT design_version_saved_is_hashed CHECK (
        status IN ('draft', 'superseded')
        OR (params_sha IS NOT NULL AND geometry_sha IS NOT NULL))
    """,
    """
    CREATE UNIQUE INDEX design_version_one_draft ON geometry.design_version (design_id)
      WHERE status = 'draft'
    """,
    f"""
    CREATE FUNCTION geometry.design_version_guard() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, geometry AS $$
    BEGIN
      IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'draft' THEN
          RAISE EXCEPTION 'ILLEGAL_STATE: a design version is created as draft, not %',
            NEW.status;
        END IF;
        RETURN NEW;
      END IF;
      IF OLD.status <> 'draft' AND {_row("NEW")} IS DISTINCT FROM {_row("OLD")} THEN
        RAISE EXCEPTION 'ILLEGAL_STATE: version % is % and immutable (INV-03)',
          OLD.id, OLD.status;
      END IF;
      IF NEW.status <> OLD.status
         AND (OLD.status, NEW.status) NOT IN ({_PAIRS}) THEN
        RAISE EXCEPTION 'ILLEGAL_STATE: % -> % is not a design version transition',
          OLD.status, NEW.status;
      END IF;
      RETURN NEW;
    END
    $$
    """,
    "REVOKE ALL ON FUNCTION geometry.design_version_guard() FROM PUBLIC",
    """
    CREATE TRIGGER design_version_guard BEFORE INSERT OR UPDATE ON geometry.design_version
      FOR EACH ROW EXECUTE FUNCTION geometry.design_version_guard()
    """,
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations: write a new migration instead")
