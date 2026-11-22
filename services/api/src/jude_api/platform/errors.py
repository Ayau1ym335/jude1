"""EH-API: every refusal and failure leaves the API as a DS-24 ErrorResponse (XC-FND-11).

    {"error": CODE, "http_status": n, "message_ru": "...", "gates": [{code, detail, link}],
     "correlation_id": "..."}

- Domain code raises ``ApiError(code, gates=...)``; the code must be a catalogued ``refusal``
  (error_catalogue.json, error/1, TSK-API-02-A; frozen at M0 exit, IDR-05). Gates may carry any
  catalogued code, e.g. kernel reason codes of a rejected op (``kind`` kernel/job/measurement).
  ``tools/contract/error_catalogue.py`` checks the catalogue against the FS and RTM in CI.
- Framework errors map to NOT_FOUND / METHOD_NOT_ALLOWED / REQUEST_INVALID. Validation gates
  name the field location only; submitted values are never echoed.
- Unhandled exceptions become 500 INTERNAL in the request middleware (it owns the correlation
  context); details stay out of the response and out of the log text.
Message text comes from the Russian resource file by key (NFR-05).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from jude_platform import correlation

HERE = Path(__file__).resolve().parent


@cache
def catalogue() -> Mapping[str, Mapping[str, Any]]:
    doc = json.loads((HERE / "error_catalogue.json").read_text(encoding="utf-8"))
    codes: Mapping[str, Mapping[str, Any]] = doc["codes"]
    return codes


@cache
def messages_ru() -> Mapping[str, str]:
    doc: Mapping[str, str] = json.loads((HERE / "messages_ru.json").read_text(encoding="utf-8"))
    return doc


@dataclass(frozen=True)
class Gate:
    code: str
    detail: str | None = None
    link: str | None = None


@dataclass
class ApiError(Exception):
    """A refusal with a catalogued code (DS-24)."""

    code: str
    gates: Sequence[Gate] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        entry = catalogue().get(self.code)
        if entry is None:
            raise KeyError(f"error code {self.code!r} is not in the error catalogue")
        if entry["kind"] != "refusal":
            raise ValueError(f"{self.code} is a {entry['kind']} code, not an HTTP refusal")
        for gate in self.gates:
            if gate.code not in catalogue():
                raise KeyError(f"gate code {gate.code!r} is not in the error catalogue")

    @property
    def http_status(self) -> int:
        return int(catalogue()[self.code]["http_status"])


def error_body(code: str, gates: Sequence[Gate] = ()) -> dict[str, Any]:
    entry = catalogue()[code]
    return {
        "error": code,
        "http_status": int(entry["http_status"]),
        "message_ru": messages_ru()[entry["message_key"]],
        "gates": [{"code": g.code, "detail": g.detail, "link": g.link} for g in gates],
        "correlation_id": correlation.current(),
    }


def error_response(code: str, gates: Sequence[Gate] = ()) -> JSONResponse:
    body = error_body(code, gates)
    return JSONResponse(status_code=body["http_status"], content=body)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.code, exc.gates)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        gates = [
            Gate(code="REQUEST_INVALID", detail=".".join(str(p) for p in err.get("loc", ())))
            for err in exc.errors()
        ]
        return error_response("REQUEST_INVALID", gates)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 422: "REQUEST_INVALID"}.get(
            exc.status_code, "INTERNAL"
        )
        return error_response(code)
