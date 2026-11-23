"""Audit events carry the UI session id (DATA-19); append_event takes it.

Revision ID: 0002_audit_ui_session
Revises: 0001_baseline
Create Date: 2026-11-23
Task: TSK-AUD-01-A

DATA-19: audit events shall carry a UI session identifier so that active time per workflow
step can be derived. The column sits outside the hashed core (ALG-58 lists the core fields);
like every audit_event column it is append-only (trigger audit_event_no_update_delete).
append_event gains a trailing p_ui_session_id DEFAULT NULL, so existing calls keep working.
"""

from alembic import op

revision = "0002_audit_ui_session"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

STATEMENTS = [
    "ALTER TABLE audit.audit_event ADD COLUMN ui_session_id text NULL "
    "CHECK (ui_session_id ~ '^[A-Za-z0-9-]{8,64}$')",
    """
    DROP FUNCTION audit.append_event(bigint, text, uuid, text, text, text, integer, text,
                                     timestamptz, char, char, jsonb, jsonb)
    """,
    """
    CREATE FUNCTION audit.append_event(
      p_seq bigint, p_type text, p_user_id uuid, p_role text,
      p_object_type text, p_object_id text, p_object_version integer, p_case_id text,
      p_at_utc timestamptz, p_prev_hash char(64), p_hash char(64),
      p_summary_before jsonb DEFAULT NULL, p_summary_after jsonb DEFAULT NULL,
      p_ui_session_id text DEFAULT NULL
    ) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
      head audit.chain_head%ROWTYPE;
    BEGIN
      SELECT * INTO head FROM audit.chain_head WHERE id FOR UPDATE;
      IF p_seq <> head.last_seq + 1 THEN
        RAISE EXCEPTION 'audit seq % does not follow chain head %', p_seq, head.last_seq
          USING ERRCODE = 'serialization_failure';
      END IF;
      IF p_prev_hash IS DISTINCT FROM head.last_hash THEN
        RAISE EXCEPTION 'audit prev_hash does not match chain head at seq %', head.last_seq
          USING ERRCODE = 'serialization_failure';
      END IF;
      INSERT INTO audit.audit_event (seq, type, user_id, role, object_type, object_id,
                                     object_version, case_id, at_utc, prev_hash, hash,
                                     ui_session_id)
      VALUES (p_seq, p_type, p_user_id, p_role, p_object_type, p_object_id,
              p_object_version, p_case_id, p_at_utc, p_prev_hash, p_hash, p_ui_session_id);
      IF p_summary_before IS NOT NULL OR p_summary_after IS NOT NULL THEN
        INSERT INTO audit.audit_summary (seq, summary_before, summary_after)
        VALUES (p_seq, p_summary_before, p_summary_after);
      END IF;
      UPDATE audit.chain_head SET last_seq = p_seq, last_hash = p_hash WHERE id;
      RETURN p_seq;
    END $$
    """,
    "REVOKE ALL ON FUNCTION audit.append_event FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION audit.append_event TO audit_append",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations: write a new migration instead")
