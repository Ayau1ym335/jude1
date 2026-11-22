"""FN-API-02 / TSK-API-02-A: only catalogued refusals become HTTP errors; gates are catalogued."""

from fastapi.testclient import TestClient
import pytest

from jude_api.main import API_PREFIX, create_app
from jude_api.platform.errors import ApiError, Gate, catalogue, error_body, messages_ru


def test_refusal_codes_map_to_their_status_and_message() -> None:
    body = error_body("PRESCRIPTION_MISSING", [Gate(code="PRESCRIPTION_MISSING")])
    assert body["http_status"] == 409
    assert body["message_ru"] == messages_ru()["error.prescription_missing"]


def test_non_refusal_codes_cannot_be_raised_but_can_be_gates() -> None:
    with pytest.raises(ValueError, match="kernel code"):
        ApiError("SELF_INTERSECTION_CREATED")
    with pytest.raises(ValueError, match="warning code"):
        ApiError("DUPLICATE_CLINIC_REF")
    err = ApiError("VALIDITY_FAILED", gates=[Gate(code="SELF_INTERSECTION_CREATED", detail="op 3")])
    assert err.http_status == 409


def test_unknown_codes_are_programming_errors() -> None:
    with pytest.raises(KeyError):
        ApiError("NO_SUCH_CODE")
    with pytest.raises(KeyError):
        ApiError("VALIDITY_FAILED", gates=[Gate(code="NO_SUCH_CODE")])


def test_every_refusal_round_trips_through_the_api() -> None:
    app = create_app(db_check=lambda: None, readiness_checks={})
    refusals = sorted(c for c, e in catalogue().items() if e["kind"] == "refusal")

    @app.get(f"{API_PREFIX}/_refuse/{{code}}")
    def refuse(code: str) -> None:
        raise ApiError(code)

    client = TestClient(app, raise_server_exceptions=False)
    for code in refusals:
        resp = client.get(f"{API_PREFIX}/_refuse/{code}")
        assert resp.status_code == catalogue()[code]["http_status"], code
        assert resp.json()["error"] == code
        assert resp.json()["message_ru"]
