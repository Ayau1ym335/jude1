from fastapi.testclient import TestClient

from jude_api.main import create_app


def _ok() -> None:
    return None


def _fail() -> None:
    raise OSError("connection refused")


def test_health_ok_when_database_reachable() -> None:
    client = TestClient(create_app(db_check=_ok))
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"database": "ok"}}


def test_health_503_when_database_unreachable() -> None:
    client = TestClient(create_app(db_check=_fail))
    resp = client.get("/api/v1/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["checks"]["database"] == "fail"
    assert "connection refused" not in resp.text


def test_health_is_only_served_under_v1_prefix() -> None:
    client = TestClient(create_app(db_check=_ok))
    assert client.get("/health").status_code == 404
