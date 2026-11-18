"""DS-05 OpResult: what every kernel op returns (IF-03).

``OpOutcome`` is what an op function produces; the runner turns it into an ``OpResult`` by
stamping the op type/version, kernel version, container image digest and library versions.
``rejected`` and ``failed`` results never carry output geometry (SAF-09).
``timings_ms`` is diagnostic only, filled by the worker (the kernel has no clock), and is
excluded from every hash.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
import re
from types import MappingProxyType
from typing import Any

from jude_kernel.core.errors import KernelContractError
from jude_kernel.core.mesh import MeshArrays

REASON_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class OpStatus(StrEnum):
    OK = "ok"
    REJECTED = "rejected"
    FAILED = "failed"


def _frozen(mapping: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(mapping or {}))


def _check_status(
    status: OpStatus, outputs: Mapping[str, MeshArrays], reason_code: str | None
) -> None:
    if not isinstance(status, OpStatus):
        raise KernelContractError(f"status must be an OpStatus, got {status!r}")
    for name, value in outputs.items():
        if not isinstance(value, MeshArrays):
            raise KernelContractError(f"output {name!r} must be a MeshArrays")
    if status is OpStatus.OK:
        if reason_code is not None:
            raise KernelContractError("an ok result carries no reason_code")
    else:
        if outputs:
            raise KernelContractError(f"a {status} result must not carry outputs (SAF-09)")
        if reason_code is None or not REASON_CODE_RE.fullmatch(reason_code):
            raise KernelContractError(f"a {status} result needs an UPPER_SNAKE reason_code")


@dataclass(frozen=True)
class OpOutcome:
    """Unstamped return value of an op function."""

    status: OpStatus
    outputs: Mapping[str, MeshArrays] = field(default_factory=dict)
    report: Mapping[str, Any] = field(default_factory=dict)
    reason_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "outputs", _frozen(self.outputs))
        object.__setattr__(self, "report", _frozen(self.report))
        _check_status(self.status, self.outputs, self.reason_code)

    @classmethod
    def ok(
        cls, outputs: Mapping[str, MeshArrays], report: Mapping[str, Any] | None = None
    ) -> "OpOutcome":
        return cls(OpStatus.OK, outputs, report or {})

    @classmethod
    def rejected(cls, reason_code: str, report: Mapping[str, Any] | None = None) -> "OpOutcome":
        return cls(OpStatus.REJECTED, {}, report or {}, reason_code)

    @classmethod
    def failed(cls, reason_code: str, report: Mapping[str, Any] | None = None) -> "OpOutcome":
        return cls(OpStatus.FAILED, {}, report or {}, reason_code)


@dataclass(frozen=True)
class OpResult:
    """DS-05, stamped by the runner (IF-03)."""

    status: OpStatus
    op_type: str
    op_version: int
    outputs: Mapping[str, MeshArrays]
    report: Mapping[str, Any]
    reason_code: str | None
    kernel_version: str
    image_digest: str
    lib_versions: Mapping[str, str]
    timings_ms: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("outputs", "report", "lib_versions", "timings_ms"):
            object.__setattr__(self, name, _frozen(getattr(self, name)))
        _check_status(self.status, self.outputs, self.reason_code)
        if not IMAGE_DIGEST_RE.fullmatch(self.image_digest):
            raise KernelContractError("image_digest must be 'sha256:<64 hex>'")
        if self.op_version < 1:
            raise KernelContractError("op_version must be >= 1")
