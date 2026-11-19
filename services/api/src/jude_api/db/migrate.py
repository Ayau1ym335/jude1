"""Forward-only schema migrations (Alembic), XC-FND-05.

Migrations ship inside the jude_api package (``jude_api/migrations``) so the API image can
apply them without the source tree. There is no downgrade: a fix is a new migration.

CLI (reads JUDE_DATABASE_URL):
  jude-migrate upgrade [REVISION]   apply migrations up to REVISION (default: head)
  jude-migrate current              print the applied revision
  jude-migrate sql [REVISION]       print the SQL instead of running it (for review)
"""

import os
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config

from jude_platform.logs import configure_logging

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
USAGE = "usage: jude-migrate {upgrade [REV] | current | sql [REV]}"


def sqlalchemy_url(url: str) -> str:
    """Map a libpq URL (postgresql://...) to the SQLAlchemy psycopg 3 dialect."""
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    raise ValueError("database URL must start with postgresql:// or postgres://")


def alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    # ConfigParser interpolation: a literal % (e.g. URL-encoded password) must be doubled.
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url(url).replace("%", "%%"))
    return cfg


def upgrade(url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    url = os.environ.get("JUDE_DATABASE_URL")
    if not url or not args:
        sys.stderr.write(USAGE + "\n(JUDE_DATABASE_URL must be set)\n")
        return 2
    # JSON logs; Alembic's progress lines ("Running upgrade ...") carry revision ids only.
    configure_logging("migrate", distribution="jude-api")
    cfg = alembic_config(url)
    match args:
        case ["upgrade"]:
            command.upgrade(cfg, "head")
        case ["upgrade", rev]:
            command.upgrade(cfg, rev)
        case ["current"]:
            command.current(cfg, verbose=True)
        case ["sql"]:
            command.upgrade(cfg, "head", sql=True)
        case ["sql", rev]:
            command.upgrade(cfg, rev, sql=True)
        case _:
            sys.stderr.write(USAGE + "\n")
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
