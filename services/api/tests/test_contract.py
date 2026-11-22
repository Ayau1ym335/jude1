"""Contract of record (XC-FND-06, IF-01): the exported OpenAPI matches what the API does."""

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from jude_api.contract import canonical_json, main, openapi_document
from jude_api.main import API_CONTRACT_VERSION, API_PREFIX, create_app
from jude_api.platform.errors import ApiError, catalogue, error_body
from jude_api.platform.schemas import ErrorResponse, HealthResponse

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[3]
METHODS = {"get", "put", "post", "delete", "patch"}


def test_committed_contract_is_current() -> None:
    assert main(["--check", str(ROOT / "packages/contracts/openapi.json")]) == 0


def test_export_is_deterministic() -> None:
    assert canonical_json(openapi_document()) == canonical_json(openapi_document())


def test_document_shape() -> None:
    doc = openapi_document()
    assert doc["openapi"].startswith("3.1")
    assert doc["info"]["version"] == API_CONTRACT_VERSION
    ops = [
        (path, method, op)
        for path, item in doc["paths"].items()
        for method, op in item.items()
        if method in METHODS
    ]
    assert ops
    for path, _method, op in ops:
        assert path.startswith(API_PREFIX + "/"), path  # probes stay out of the contract
        ref = op["responses"]["default"]["content"]["application/json"]["schema"]["$ref"]
        assert ref == "#/components/schemas/ErrorResponse"
    op_ids = [op["operationId"] for _p, _m, op in ops]
    assert len(op_ids) == len(set(op_ids))


@pytest.mark.parametrize(
    "code", sorted(c for c, e in catalogue().items() if e["kind"] == "refusal")
)
def test_every_error_body_matches_the_published_schema(code: str) -> None:
    ErrorResponse.model_validate(error_body(code))


def test_live_error_and_health_responses_match_schemas() -> None:
    app = create_app(db_check=lambda: None, readiness_checks={})

    @app.get(f"{API_PREFIX}/_contract_probe")
    def probe() -> None:
        raise ApiError("NOT_FOUND")

    client = TestClient(app)
    HealthResponse.model_validate(client.get(f"{API_PREFIX}/health").json())
    for resp in (client.get(f"{API_PREFIX}/_contract_probe"), client.get(f"{API_PREFIX}/nope")):
        body = ErrorResponse.model_validate(resp.json())
        assert body.correlation_id == resp.headers["X-Correlation-ID"]
