"""Integration fixtures: a fresh, empty database per test module (XC-FND-05).

Needs a disposable Postgres server reachable through JUDE_TEST_ADMIN_URL (a superuser URL
to its maintenance database), e.g. started by `just test-int` or the CI service container.
Never point it at a database that holds data: the fixtures create and drop databases.
"""

from collections.abc import Iterator
import os
from urllib.parse import urlsplit, urlunsplit
import uuid

import psycopg
import pytest

from jude_api.db.migrate import upgrade


def admin_url() -> str:
    url = os.environ.get("JUDE_TEST_ADMIN_URL")
    if not url:
        pytest.fail("JUDE_TEST_ADMIN_URL is not set (start a test server with `just test-int`)")
    return url


def url_for_db(url: str, dbname: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


def create_empty_db() -> str:
    name = f"jude_it_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(admin_url(), autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    return name


def drop_db(name: str) -> None:
    with psycopg.connect(admin_url(), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="module")
def migrated_url() -> Iterator[str]:
    """URL of a new empty database after `upgrade head`."""
    name = create_empty_db()
    url = url_for_db(admin_url(), name)
    try:
        upgrade(url)
        yield url
    finally:
        drop_db(name)


@pytest.fixture
def empty_db_url() -> Iterator[str]:
    """URL of a new empty database that has not been migrated."""
    name = create_empty_db()
    try:
        yield url_for_db(admin_url(), name)
    finally:
        drop_db(name)


@pytest.fixture
def conn(migrated_url: str) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """Connection whose work is rolled back after each test."""
    with psycopg.connect(migrated_url) as c:
        yield c
        c.rollback()
