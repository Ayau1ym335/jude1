"""UT-FN-IAM-01: login helpers, configuration and request validation (no database)."""

import hashlib

from fastapi.testclient import TestClient
import pytest

from jude_api.domain.iam.login import hash_password, normalise_login, token_hash
from jude_api.domain.iam.routes import AUTH_PREFIX
from jude_api.main import create_app
from jude_api.platform import deps
from jude_api.platform.security_config import SecurityConfig, security_config


def test_login_normalisation() -> None:
    assert normalise_login("  Tech.One ") == "tech.one"
    assert normalise_login("STRASSE") == normalise_login("straße")  # case-folding, not lower()


def test_password_hash_is_argon2id() -> None:
    encoded = hash_password("x" * 12)
    assert encoded.startswith("$argon2id$v=19$")
    assert hash_password("x" * 12) != encoded  # salted


def test_token_hash() -> None:
    assert token_hash("abc") == hashlib.sha256(b"abc").hexdigest()


def test_shipped_security_config_is_sd01_sd02() -> None:
    cfg = security_config()
    assert (cfg.max_failures, cfg.window_seconds, cfg.lock_seconds) == (5, 900, 900)
    assert cfg.idle_timeout_seconds == 1800
    with pytest.raises(ValueError):
        SecurityConfig(0, 900, 900, 1800, 60)


def test_login_body_is_validated_before_any_database_use() -> None:
    app = create_app(db_check=lambda: None, readiness_checks={})
    app.dependency_overrides[deps.db] = lambda: None
    api = TestClient(app)
    r = api.post(f"{AUTH_PREFIX}/login", json={"login": "", "password": "x"})
    assert r.status_code == 422 and r.json()["error"] == "REQUEST_INVALID"
    r = api.post(f"{AUTH_PREFIX}/login", json={"login": "a", "password": "x", "extra": 1})
    assert r.status_code == 422
    assert "set-cookie" not in r.headers
