"""First clinic admin (TSK-IAM-05-B; FN-IAM-05, SEC-01, SEC-19).

FN-IAM-05 needs a clinic admin to create accounts, so the first admin has to come from outside
the API. This command creates it on an operator's console:

  jude-admin create-first-admin --login L --display-name "Name"

(runbook: docs/runbooks/FN-IAM-05-first-admin.md)

- It works only while there is **no active clinic admin**. Otherwise it refuses, so it cannot
  become a second, unaudited way to create admins. An advisory lock serialises two runs.
- The password is never an argument, so it stays out of shell history and the process list.
  On a terminal it is prompted without echo; otherwise it is the first line of standard input.
  It is stored as argon2id only.
- It uses the same service as the API: named person, unique login, password policy, and one
  ``user.created`` audit event. The actor is user_id NULL with role ``system``.
- Exit codes: 0 created (prints the new id), 1 refused, 2 usage.
"""

import argparse
import getpass
import os
import sys
from typing import Final

import psycopg

from jude_api.domain.iam.users import (
    PASSWORD_MIN_LENGTH,
    Actor,
    active_admin_exists,
    create_user,
)
from jude_api.platform.deps import APP_ROLE
from jude_api.platform.errors import ApiError

BOOTSTRAP_LOCK: Final = 0x4A554445_0005  # "JUDE" + task number; any fixed key works
SYSTEM: Final = Actor(user_id=None, role="system")


def create_first_admin(
    conn: psycopg.Connection[tuple[object, ...]], login: str, display_name: str, password: str
) -> str:
    """Return the new admin's id, or raise ApiError / RuntimeError (refused)."""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise RuntimeError(f"password shorter than {PASSWORD_MIN_LENGTH} characters")
    with conn.transaction():
        conn.execute(f"SET LOCAL ROLE {APP_ROLE}")
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (BOOTSTRAP_LOCK,))
        if active_admin_exists(conn):
            raise RuntimeError("an active clinic admin exists: create accounts in the app")
        user = create_user(
            conn, SYSTEM, display_name=display_name, login=login, role="clinic_admin",
            password=password,
        )  # fmt: skip
    return str(user["id"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jude-admin")
    sub = parser.add_subparsers(dest="command", required=True)
    first = sub.add_parser("create-first-admin", help="create the first clinic admin")
    first.add_argument("--login", required=True)
    first.add_argument("--display-name", required=True)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    url = os.environ.get("JUDE_DATABASE_URL")
    if not url:
        sys.stderr.write("JUDE_DATABASE_URL must be set\n")
        return 2
    if sys.stdin.isatty():
        password = getpass.getpass("Password: ")
    else:
        password = sys.stdin.readline().rstrip("\r\n")
    try:
        with psycopg.connect(url) as conn:
            new_id = create_first_admin(conn, args.login, args.display_name, password)
    except ApiError as exc:
        sys.stderr.write(f"refused: {exc.code}\n")
        return 1
    except RuntimeError as exc:
        sys.stderr.write(f"refused: {exc}\n")
        return 1
    sys.stdout.write(new_id + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
