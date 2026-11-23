"""IAM accounts, login failures and server-side sessions (FN-IAM-01/02, IDR-08).

Revision ID: 0003_iam_accounts
Revises: 0002_audit_ui_session
Create Date: 2026-11-23
Task: TSK-IAM-01-B

- governance."user": named person (SEC-01), unique case-folded login, role from FR-130
  {technician, clinic_admin}, password only as an argon2id encoding (SEC-05), active flag
  (SEC-19, accounts are deactivated, never deleted), locked_until (SD-01 lockout).
- governance.login_failure: one row per failed password check, counted in the SD-01 window.
- governance.session: keyed by SHA-256 of the session token; the CSRF token is stored as its
  SHA-256 too, so a read of this table cannot be replayed as a session (FN-IAM-01/02).
- app_rw: read/write; DELETE only on session (logout, expiry) and login_failure (cleared on a
  successful login). No DELETE on users (SEC-19).

The foreign keys from created_by / *_by columns to governance."user" come with account
management (TSK-IAM-05-B), which also creates the first clinic admin.
"""

from alembic import op

revision = "0003_iam_accounts"
down_revision = "0002_audit_ui_session"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE governance."user" (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      login text NOT NULL UNIQUE
        CHECK (login = lower(btrim(login)) AND length(login) BETWEEN 1 AND 64),
      display_name text NOT NULL CHECK (length(btrim(display_name)) BETWEEN 1 AND 128),
      role text NOT NULL CHECK (role IN ('technician', 'clinic_admin')),
      password_hash text NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
      active boolean NOT NULL DEFAULT true,
      locked_until timestamptz NULL,
      created_by uuid NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE governance.login_failure (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      user_id uuid NOT NULL REFERENCES governance."user"(id),
      at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX login_failure_window ON governance.login_failure (user_id, at)",
    """
    CREATE TABLE governance.session (
      id char(64) PRIMARY KEY CHECK (id ~ '^[0-9a-f]{64}$'),
      user_id uuid NOT NULL REFERENCES governance."user"(id),
      csrf_hash char(64) NOT NULL CHECK (csrf_hash ~ '^[0-9a-f]{64}$'),
      ui_session_id text NOT NULL CHECK (ui_session_id ~ '^[A-Za-z0-9-]{8,64}$'),
      created_at timestamptz NOT NULL DEFAULT now(),
      last_seen_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX session_by_user ON governance.session (user_id)",
    'GRANT SELECT, INSERT, UPDATE ON governance."user", governance.login_failure, '
    "governance.session TO app_rw",
    "GRANT DELETE ON governance.session, governance.login_failure TO app_rw",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations: write a new migration instead")
