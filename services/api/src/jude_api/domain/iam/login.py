"""FN-IAM-01 Authenticate user (TSK-IAM-01-B; SEC-01, SEC-05, SEC-19, SEC-20, IDR-08).

``authenticate`` runs in the request transaction and returns an outcome instead of raising,
because a failed login must still commit its failure row and audit event before the API
answers 401 / 423.

Rules (FN-IAM-01 steps 1-7):
- login is trimmed and case-folded; an unknown login runs a dummy argon2id verify, so its
  timing does not reveal whether the account exists (no user enumeration);
- a locked account (locked_until > now) is refused with ACCOUNT_LOCKED before any verify;
- a wrong password inserts a failure row; when the failures in the last ``window_seconds``
  reach ``max_failures`` (SD-01, security.json) the account is locked for ``lock_seconds``;
- a deactivated account answers like a wrong password (BAD_CREDENTIALS);
- success clears the failure rows and creates a server-side session: 256-bit random session
  and CSRF tokens, stored only as SHA-256; the browser gets the session token in an httpOnly
  cookie and the CSRF token in the body.

Audit (FN-AUD-01): every attempt writes exactly one ``auth.login`` or ``auth.login_failed``
event; the attempt that locks the account also writes ``account.locked`` (SEC-05). The
submitted login and the client address are never stored or logged.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import secrets
from typing import Any, Literal
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
import psycopg

from jude_api.platform import aud
from jude_api.platform.security_config import SecurityConfig

HASHER = PasswordHasher()  # argon2id, RFC 9106 parameters of argon2-cffi
_DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


def normalise_login(login: str) -> str:
    return login.strip().casefold()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def hash_password(password: str) -> str:
    return HASHER.hash(password)


def _verify(encoded: str, password: str) -> bool:
    try:
        return HASHER.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


@dataclass(frozen=True)
class LoginSuccess:
    user_id: uuid.UUID
    display_name: str
    role: str
    session_token: str
    csrf_token: str
    ui_session_id: str
    kind: Literal["ok"] = "ok"


@dataclass(frozen=True)
class LoginRefused:
    code: Literal["BAD_CREDENTIALS", "ACCOUNT_LOCKED"]
    locked_until: datetime | None = None
    kind: Literal["refused"] = "refused"


def _failed(conn: psycopg.Connection[Any], user: tuple[Any, ...] | None, reason: str) -> None:
    event = aud.AuditEvent(
        "auth.login_failed",
        user[0] if user else None,
        user[2] if user else None,
        object_type="user" if user else None,
        object_id=str(user[0]) if user else None,
        summary_after={"reason": reason},
    )
    aud.append(conn, event)


def authenticate(
    conn: psycopg.Connection[Any], login: str, password: str, cfg: SecurityConfig, now: datetime
) -> LoginSuccess | LoginRefused:
    """One login attempt inside the caller's open transaction (commit it in both outcomes)."""
    user = conn.execute(
        'SELECT id, display_name, role, password_hash, active, locked_until FROM governance."user"'
        " WHERE login = %s FOR UPDATE",
        (normalise_login(login),),
    ).fetchone()
    if user is None:
        _verify(_DUMMY_HASH, password)
        _failed(conn, None, "unknown_login")
        return LoginRefused("BAD_CREDENTIALS")
    uid, name, role, encoded, active, locked_until = user
    if locked_until is not None and locked_until > now:
        _failed(conn, user, "locked")
        return LoginRefused("ACCOUNT_LOCKED", locked_until)
    if not _verify(encoded, password) or not active:
        reason = "deactivated" if not active else "bad_password"
        if active:
            conn.execute(
                "INSERT INTO governance.login_failure (user_id, at) VALUES (%s, %s)", (uid, now)
            )
            row = conn.execute(
                "SELECT count(*) FROM governance.login_failure WHERE user_id = %s AND at > %s",
                (uid, now - timedelta(seconds=cfg.window_seconds)),
            ).fetchone()
            if row is not None and row[0] >= cfg.max_failures:
                until = now + timedelta(seconds=cfg.lock_seconds)
                conn.execute(
                    'UPDATE governance."user" SET locked_until = %s, updated_at = %s WHERE id = %s',
                    (until, now, uid),
                )
                locked = aud.AuditEvent(
                    "account.locked", uid, role, object_type="user", object_id=str(uid),
                    summary_after={"locked_until": until.isoformat()},
                )  # fmt: skip
                aud.append(conn, locked)
        _failed(conn, user, reason)
        return LoginRefused("BAD_CREDENTIALS")
    conn.execute("DELETE FROM governance.login_failure WHERE user_id = %s", (uid,))
    session_token, csrf_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    ui_session_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO governance.session (id, user_id, csrf_hash, ui_session_id, created_at,"
        " last_seen_at) VALUES (%s, %s, %s, %s, %s, %s)",
        (token_hash(session_token), uid, token_hash(csrf_token), ui_session_id, now, now),
    )
    success = aud.AuditEvent(
        "auth.login", uid, role, object_type="user", object_id=str(uid), ui_session_id=ui_session_id
    )
    aud.append(conn, success)
    return LoginSuccess(uid, name, role, session_token, csrf_token, ui_session_id)
