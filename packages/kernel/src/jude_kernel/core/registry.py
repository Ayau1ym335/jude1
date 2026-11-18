"""DS-03 OpSpec and the op registry (FN-KRP-04 contract part).

A registry is an immutable value built once from OpSpecs; there is no mutable global
registration (kernel purity, IF-03). Only functions defined inside ``jude_kernel`` can be
registered, so the runner never executes code from a layer that may do I/O.

Parameter validation against ``params_schema`` (PARAM_NOT_SET / PARAM_INVALID, the
"no defaults" schema rule) is TSK-KRP-04-K; the runner takes the validator as an explicit
argument so an op can never run unvalidated by accident.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
import re
from types import MappingProxyType
from typing import Any

from jude_kernel.core.errors import KernelContractError
from jude_kernel.core.mesh import MeshArrays
from jude_kernel.core.result import OpOutcome

OP_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
KIND_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
KERNEL_PACKAGE = "jude_kernel"

OpFn = Callable[[Mapping[str, MeshArrays], Mapping[str, Any]], OpOutcome]


@dataclass(frozen=True)
class OpSpec:
    """Registry entry: every behaviour change bumps ``version`` (FN-KRP-04)."""

    type: str
    version: int
    fn: OpFn
    params_schema: Mapping[str, Any]
    input_kinds: tuple[str, ...]
    output_kinds: tuple[str, ...]
    topology_preserving: bool
    guard: bool
    idempotent: bool
    description: str = field(default="")

    def __post_init__(self) -> None:
        if not OP_TYPE_RE.fullmatch(self.type):
            raise KernelContractError(f"op type {self.type!r} is not a dotted lower-case name")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise KernelContractError(f"{self.type}: version must be an int >= 1")
        module = getattr(self.fn, "__module__", "") or ""
        if module != KERNEL_PACKAGE and not module.startswith(KERNEL_PACKAGE + "."):
            raise KernelContractError(
                f"{self.type}: op function must live in {KERNEL_PACKAGE} (got module {module!r})"
            )
        for kinds in (self.input_kinds, self.output_kinds):
            if len(set(kinds)) != len(kinds) or not all(KIND_RE.fullmatch(k) for k in kinds):
                raise KernelContractError(f"{self.type}: kinds must be unique lower-case names")
        if not isinstance(self.params_schema, Mapping):
            raise KernelContractError(f"{self.type}: params_schema must be a JSON Schema object")
        object.__setattr__(self, "params_schema", MappingProxyType(dict(self.params_schema)))
        for flag in ("topology_preserving", "guard", "idempotent"):
            if not isinstance(getattr(self, flag), bool):
                raise KernelContractError(f"{self.type}: {flag} must be a bool")

    @property
    def key(self) -> tuple[str, int]:
        return (self.type, self.version)


class Registry:
    """Immutable (type, version) -> OpSpec map."""

    __slots__ = ("_specs",)

    def __init__(self, specs: Iterable[OpSpec]) -> None:
        table: dict[tuple[str, int], OpSpec] = {}
        for spec in specs:
            if spec.key in table:
                raise KernelContractError(f"duplicate registry entry {spec.type} v{spec.version}")
            table[spec.key] = spec
        self._specs: Mapping[tuple[str, int], OpSpec] = MappingProxyType(
            dict(sorted(table.items()))
        )

    def get(self, op_type: str, version: int) -> OpSpec | None:
        return self._specs.get((op_type, version))

    def __iter__(self) -> Any:
        return iter(self._specs.values())

    def __len__(self) -> int:
        return len(self._specs)


# The shipped registry. Ops are added by their TT-K tasks, each with an op_version.
REGISTRY = Registry(())
