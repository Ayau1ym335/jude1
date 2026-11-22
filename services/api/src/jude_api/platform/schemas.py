"""Response models shared by every endpoint of the /api/v1 contract (XC-FND-06, IF-01).

``ErrorResponse`` is DS-24 exactly as ``jude_api.platform.errors.error_body`` produces it;
every /api/v1 operation declares it as its ``default`` response, so the generated client
knows the error shape.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Gate(BaseModel):
    """One failed gate or field (DS-24 ``gates[]``)."""

    model_config = ConfigDict(extra="forbid")
    code: str
    detail: str | None = None
    link: str | None = None


class ErrorResponse(BaseModel):
    """DS-24 error envelope. ``error`` is a code from the error catalogue (IDR-05)."""

    model_config = ConfigDict(extra="forbid")
    error: str = Field(description="Error catalogue code (error/1, IDR-05)")
    http_status: int
    message_ru: str = Field(description="User-facing message, Russian (NFR-05)")
    gates: list[Gate]
    correlation_id: str | None = Field(
        description="Same value as the X-Correlation-ID response header (XC-FND-11)"
    )


ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    "default": {"model": ErrorResponse, "description": "Error (DS-24)"},
}


class HealthChecks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    database: Literal["ok", "fail"]


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "unavailable"]
    service: Literal["api"]
    checks: HealthChecks
