"""XC-FND-11: log scrubbing (completion criterion), correlation, DS-24 errors, probes.

Seeded identifiers go into every channel a request has (path, query string, headers, cookies,
JSON body, invalid body, exception message). None of them may appear in any log line. Every
line must validate against packages/platform/log-schema.json.
"""

from collections.abc import Iterator
import io
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.testclient import TestClient
import jsonschema
from pydantic import BaseModel, Field
import pytest

from jude_api.main import create_app
from jude_api.platform.errors import ApiError, Gate, catalogue
from jude_platform.logs import configure_logging

ROOT = Path(__file__).resolve().parents[3]
LOG_SCHEMA = json.loads((ROOT / "packages/platform/log-schema.json").read_text(encoding="utf-8"))

# Synthetic look-alikes of what must never be logged: a name, an IIN, a phone, an e-mail,
# a session token, a CSRF token, a file name with a name in it, a clinic reference.
NAME = "Иванова Айгерим"
IIN = "870101300123"
PHONE = "+7 701 123 45 67"
EMAIL = "aigerim@example.kz"
SESSION_SEED = "s3ssion-T0ken-9f8e7d6c"
CSRF = "csrf-Tok-1a2b3c4d"
FILE = "Ivanova_Aigerim_scan_2026.stl"
CLINIC_REF = "Карта 4711 Иванова"
SEEDS = [NAME, IIN, PHONE, EMAIL, SESSION_SEED, CSRF, FILE, CLINIC_REF, "Ivanova", "Иванова"]


class EchoIn(BaseModel):
    clinic_ref: str = Field(max_length=64)
    count: int


def _test_router() -> APIRouter:
    r = APIRouter(prefix="/api/v1/_test")

    @r.post("/echo/{case_id}")
    def echo(case_id: str, body: EchoIn) -> dict[str, str]:
        return {"case_id": case_id}

    @r.get("/boom/{case_id}")
    def boom(case_id: str) -> None:
        raise RuntimeError(f"failed on {FILE} for {NAME} {IIN} {EMAIL}")

    @r.get("/refuse")
    def refuse() -> None:
        raise ApiError("NOT_FOUND", gates=[Gate(code="NOT_FOUND", detail="case")])

    return r


def _ok() -> None:
    return None


def _fail() -> None:
    raise ConnectionError(f"db at {EMAIL} refused password={SESSION_SEED}")


@pytest.fixture
def logs() -> Iterator[io.StringIO]:
    buf = io.StringIO()
    configure_logging("api", distribution="jude-api", stream=buf)
    yield buf
    logging.getLogger().handlers = []


def _app(**checks: Any) -> TestClient:
    app = create_app(db_check=_ok, readiness_checks=checks or {"database": _ok})
    app.include_router(_test_router())
    return TestClient(app)


def _lines(buf: io.StringIO) -> list[dict[str, Any]]:
    docs = [json.loads(line) for line in buf.getvalue().splitlines() if line]
    for doc in docs:
        jsonschema.validate(doc, LOG_SCHEMA)
    return docs


def test_seeded_identifiers_never_appear_in_logs(logs: io.StringIO) -> None:
    client = _app()
    # Header values are bytes on the wire; non-ASCII ones arrive UTF-8 encoded.
    headers: dict[bytes, bytes] = {
        b"Authorization": f"Bearer {SESSION_SEED}".encode(),
        b"Cookie": f"session={SESSION_SEED}; csrf={CSRF}".encode(),
        b"X-CSRF-Token": CSRF.encode(),
        b"X-Patient-Name": NAME.encode(),
        b"User-Agent": f"browser {EMAIL}".encode(),
        b"X-Correlation-ID": b"seed-test-0001",
    }
    query = {"q": NAME, "iin": IIN, "phone": PHONE, "file": FILE}
    responses = [
        client.post(
            "/api/v1/_test/echo/J-0123ABCD",
            params=query,
            headers=headers,
            json={"clinic_ref": CLINIC_REF, "count": 1},
        ),
        client.post(
            "/api/v1/_test/echo/J-0123ABCD",
            params=query,
            headers=headers,
            json={"clinic_ref": NAME * 10, "count": IIN + " " + PHONE},
        ),
        client.get("/api/v1/_test/boom/J-0123ABCD", params=query, headers=headers),
        client.get(f"/api/v1/{NAME}/{IIN}/{FILE}", params=query, headers=headers),
        client.delete("/api/v1/_test/refuse", params=query, headers=headers),
        client.get("/api/v1/_test/refuse", params=query, headers=headers),
    ]
    assert [r.status_code for r in responses] == [200, 422, 500, 404, 405, 404]

    raw = logs.getvalue()
    leaked = [s for s in SEEDS if s in raw]
    assert leaked == [], f"seeded identifiers in logs: {leaked}"
    docs = _lines(logs)
    requests = [d for d in docs if d["event"] == "http.request"]
    assert len(requests) == len(responses)
    assert {d["route"] for d in requests} == {
        "/api/v1/_test/echo/{case_id}",
        "/api/v1/_test/boom/{case_id}",
        "unmatched",
        "/api/v1/_test/refuse",
    }
    assert all(d["correlation_id"] == "seed-test-0001" for d in docs)
    (exc,) = [d for d in docs if d["event"] == "http.unhandled_exception"]
    assert exc["exc_type"] == "builtins.RuntimeError" and exc["error_code"] == "INTERNAL"


def test_error_bodies_follow_ds24_and_echo_no_input(logs: io.StringIO) -> None:
    client = _app()
    bad = client.post("/api/v1/_test/echo/x", json={"clinic_ref": NAME * 10, "count": IIN + "x"})
    body = bad.json()
    assert set(body) == {"error", "http_status", "message_ru", "step", "gates", "correlation_id"}
    assert body["error"] == "REQUEST_INVALID" and body["http_status"] == 422
    assert {g["detail"] for g in body["gates"]} == {"body.clinic_ref", "body.count"}
    assert NAME not in bad.text and IIN not in bad.text

    boom = client.get("/api/v1/_test/boom/x")
    assert boom.status_code == 500 and boom.json()["error"] == "INTERNAL"
    assert NAME not in boom.text and FILE not in boom.text
    assert boom.json()["correlation_id"] == boom.headers["X-Correlation-ID"]

    refused = client.get("/api/v1/_test/refuse").json()
    gate = {"code": "NOT_FOUND", "detail": "case", "link": None}
    assert refused["gates"] == [gate | {"message_ru": refused["message_ru"], "step": "CURRENT"}]
    assert refused["message_ru"]


def test_correlation_header_kept_replaced_or_created(logs: io.StringIO) -> None:
    client = _app()
    kept = client.get("/api/v1/health", headers={"X-Correlation-ID": "ui-action-12345678"})
    assert kept.headers["X-Correlation-ID"] == "ui-action-12345678"
    replaced = client.get("/api/v1/health", headers={b"X-Correlation-ID": f"{NAME} 123".encode()})
    assert replaced.headers["X-Correlation-ID"].isascii()
    assert len(replaced.headers["X-Correlation-ID"]) == 32
    created = client.get("/api/v1/health")
    assert len(created.headers["X-Correlation-ID"]) == 32


def test_unknown_error_code_is_a_programming_error() -> None:
    with pytest.raises(KeyError):
        ApiError("NOT_A_CODE")
    assert all(entry["message_key"] for entry in catalogue().values())


def test_probes(logs: io.StringIO) -> None:
    client = _app(database=_ok, storage=_ok)
    assert client.get("/livez").json() == {"status": "ok", "service": "api"}
    ready = client.get("/readyz")
    assert ready.status_code == 200 and ready.json()["checks"] == {
        "database": "ok",
        "storage": "ok",
    }

    failing = _app(database=_fail, storage=_ok)
    not_ready = failing.get("/readyz")
    assert not_ready.status_code == 503
    assert not_ready.json()["checks"] == {"database": "fail", "storage": "ok"}
    assert EMAIL not in not_ready.text and SESSION_SEED not in logs.getvalue()
    assert any(
        d["event"] == "readiness.check_failed" and d["check"] == "database" for d in _lines(logs)
    )


def test_metrics_count_route_templates_only(logs: io.StringIO) -> None:
    client = _app()
    client.post(
        "/api/v1/_test/echo/J-0123ABCD", params={"q": NAME}, json={"clinic_ref": "x", "count": 1}
    )
    text = client.get("/metrics").text
    assert 'route="/api/v1/_test/echo/{case_id}",status="200"' in text
    assert "J-0123ABCD" not in text and NAME not in text
    assert "jude_build_info" in text


def test_probes_are_outside_the_public_api_prefix() -> None:
    """The proxy routes only /api/* to the API, so these stay internal (Caddyfile)."""
    app = create_app(db_check=_ok)
    paths = [app.url_path_for(name) for name in ("livez", "readyz", "metrics_text")]
    assert paths == ["/livez", "/readyz", "/metrics"]
    assert not any(p.startswith("/api/") for p in paths)
