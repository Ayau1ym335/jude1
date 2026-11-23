"""FN-IAM-05 Manage user accounts (TSK-IAM-05-B; SEC-01, SEC-19, FR-130, IDR-08).

Service functions run in the caller's transaction and raise ``ApiError`` refusals.

- **create**: the display name must name a person (non-blank after trimming, else
  NAME_REQUIRED, 422). The login is trimmed and case-folded, and must be unique (else
  LOGIN_TAKEN, 409). The password is stored only as an argon2id encoding. Emits user.created.
- **update** (role and/or active): a deactivation sets active=false, deletes every session of
  the account and emits user.deactivated. Any other change (role, reactivation) emits
  user.changed. A PATCH that changes nothing emits nothing.
- **last admin**: a change that would leave no active clinic admin is refused with LAST_ADMIN
  (409), whether it is a deactivation or a demotion, and whether it targets the caller or
  another admin. The active admin rows are locked first (FOR UPDATE), so two concurrent
  demotions cannot both pass the check.
- There is no delete: accounts are deactivated, never removed (SEC-19). app_rw has no DELETE on
  governance."user", and every *_by column references it (migration 0005).

Audit summaries carry only role and active. Logins, display names and passwords never enter
the audit log or the application log.
"""

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Final, Literal
import uuid

import psycopg

from jude_api.domain.iam.login import hash_password, normalise_login
from jude_api.platform import aud
from jude_api.platform.errors import ApiError, Gate

Role = Literal["technician", "clinic_admin"]
ADMIN: Final = "clinic_admin"
# Engineering decision (2026-11-24, delegated): minimum length of an initial password. This is
# not a clinical value. It follows NIST SP 800-63B (length over composition rules) with a
# margin above that standard's 8-character floor.
PASSWORD_MIN_LENGTH: Final = 12
LOGIN_MAX_LENGTH: Final = 64  # governance."user" CHECK
# Engineering decision (2026-11-24): a login is ASCII lower case, digits and ._@- after trimming
# and case-folding. Python's casefold and Postgres' lower() then agree, so the table's CHECK
# cannot reject a login the API accepted.
LOGIN_RE: Final = re.compile(r"[a-z0-9][a-z0-9._@-]{0,63}")
NAME_MAX_LENGTH: Final = 128  # governance."user" CHECK

_FIELDS: Final = ("id", "display_name", "login", "role", "active", "created_at")


@dataclass(frozen=True)
class Actor:
    """Who makes the change: an account, or None with role "system" (first-admin bootstrap)."""

    user_id: uuid.UUID | None
    role: str
    ui_session_id: str | None = None


def _user(row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(_FIELDS, row, strict=True))


def list_users(conn: psycopg.Connection[Any]) -> list[dict[str, Any]]:
    rows = conn.execute(
        'SELECT id, display_name, login, role, active, created_at FROM governance."user"'
        " ORDER BY login"
    ).fetchall()
    return [_user(r) for r in rows]


def create_user(
    conn: psycopg.Connection[Any],
    actor: Actor,
    *,
    display_name: str,
    login: str,
    role: Role,
    password: str,
) -> dict[str, Any]:
    name = display_name.strip()
    if not name:
        raise ApiError("NAME_REQUIRED")
    key = normalise_login(login)
    if not LOGIN_RE.fullmatch(key):
        raise ApiError("REQUEST_INVALID", gates=[Gate(code="REQUEST_INVALID", detail="body.login")])
    encoded = hash_password(password)  # before the insert: keep the row lock short
    row = conn.execute(
        """
        INSERT INTO governance."user" (login, display_name, role, password_hash, created_by)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (login) DO NOTHING
        RETURNING id, display_name, login, role, active, created_at
        """,
        (key, name, role, encoded, actor.user_id),
    ).fetchone()
    if row is None:
        raise ApiError("LOGIN_TAKEN")
    user = _user(row)
    aud.append(conn, _event("user.created", actor, user["id"], None, user))
    return user


def update_user(
    conn: psycopg.Connection[Any],
    actor: Actor,
    user_id: uuid.UUID,
    *,
    role: Role | None = None,
    active: bool | None = None,
    now: datetime,
) -> dict[str, Any]:
    # Lock the active admins first, then the target, so every admin change sees the same order.
    admins = {
        r[0]
        for r in conn.execute(
            'SELECT id FROM governance."user" WHERE role = %s AND active ORDER BY id FOR UPDATE',
            (ADMIN,),
        ).fetchall()
    }
    row = conn.execute(
        'SELECT id, display_name, login, role, active, created_at FROM governance."user"'
        " WHERE id = %s FOR UPDATE",
        (user_id,),
    ).fetchone()
    if row is None:
        raise ApiError("NOT_FOUND")
    before = _user(row)
    after = {
        **before,
        "role": before["role"] if role is None else role,
        "active": before["active"] if active is None else active,
    }
    if (after["role"], after["active"]) == (before["role"], before["active"]):
        return before  # nothing changes, nothing to record
    still_admin = after["role"] == ADMIN and after["active"]
    if user_id in admins and not still_admin and len(admins) == 1:
        raise ApiError("LAST_ADMIN")
    conn.execute(
        'UPDATE governance."user" SET role = %s, active = %s, updated_at = %s WHERE id = %s',
        (after["role"], after["active"], now, user_id),
    )
    deactivated = before["active"] and not after["active"]
    if deactivated:  # active sessions end now (FN-IAM-05 step 3)
        conn.execute("DELETE FROM governance.session WHERE user_id = %s", (user_id,))
    etype = "user.deactivated" if deactivated else "user.changed"
    aud.append(conn, _event(etype, actor, user_id, before, after))
    return after


def active_admin_exists(conn: psycopg.Connection[Any]) -> bool:
    row = conn.execute(
        'SELECT EXISTS (SELECT 1 FROM governance."user" WHERE role = %s AND active)', (ADMIN,)
    ).fetchone()
    return bool(row and row[0])


def _event(
    etype: str,
    actor: Actor,
    user_id: uuid.UUID,
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> aud.AuditEvent:
    def summary(u: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if u is None else {"role": u["role"], "active": u["active"]}

    return aud.AuditEvent(
        etype, actor.user_id, actor.role, object_type="user", object_id=str(user_id),
        summary_before=summary(before), summary_after=summary(after),
        ui_session_id=actor.ui_session_id,
    )  # fmt: skip
