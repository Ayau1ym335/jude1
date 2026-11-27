"""FN-KRP-01 Op-log replay engine (ALG-53; FR-052, FR-053, FR-023, SAF-09, VER-07, UR-03).

Regenerates a design from what is recorded about it (ADR-003), never from a geometry snapshot:

    stage 1 (FN-KRP-01.1)  original (F_file) -> units.to_mm -> enabled cleanup ops -> scan_prepared
    frame                  scan_prepared (F_scan) -> confirmed frame F_scan->F_anat
    stage 2 (FN-KRP-01.2)  enabled design ops in seq order -> closure, the pinned terminal op
                           (IDR-01: recorded, always evaluated last, position not editable)

**Op contract inside the fold.** Each op is looked up in the registry by (type, op_version)
(FN-KRP-04), so the engine knows no individual op. A replayed op takes the current geometry as
its single input ``mesh`` and returns a single output ``mesh``; a registry entry with other
kinds cannot be replayed and is a caller bug (``KernelContractError``). Params are validated
before anything runs; the op runs through the IF-03 runner.

**Per-op cache (FN-KRP-01.3).** The key of each step is

    SHA-256(JCS({"input_geometry_sha", "type", "op_version", "params", "kernel_version"}))

The kernel holds no state: the caller passes the entries it has (``cache``, key -> mesh) and
receives the entries this run produced (``ReplayResult.new_cache``) to store as blobs. A key
from another kernel version never matches, because the kernel version is part of the key.
Editing op k changes the input sha of every later step, so only ops k..n recompute. Only ``ok``
outputs are cached. The result never depends on whether the cache was warm.

**Failure (FN-KRP-01.4, SAF-09).** The first rejected or failed step stops the replay. The
result carries the code, the stopping step, and the last valid geometry, which is the output
of the step before it. That geometry is never a design result: ``status`` is not ``ok``. The
steps after it are reported as ``not_run``.

**Blobs.** The original is resolved from ``blobs`` by its geometry sha (FN-KRP-02). A missing
blob, or one whose content does not hash to its sha, is ``BLOB_MISSING`` (an integrity
incident): the replay does not start.

Disabled ops are skipped but listed (TC-FR-053: disable then re-enable returns the prior hash,
since a skipped op leaves the input sha of the next step unchanged).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
from types import MappingProxyType
from typing import Any, Final

from jude_kernel.core.errors import KernelContractError
from jude_kernel.core.mesh import Frame, MeshArrays
from jude_kernel.core.registry import Registry
from jude_kernel.core.result import OpStatus
from jude_kernel.core.runner import run
from jude_kernel.k03_frames.transform import RigidTransform
from jude_kernel.k08_replay.geometry_hash import mesh_geometry_sha256
from jude_kernel.k08_replay.jcs import jcs_bytes
from jude_kernel.k08_replay.op_params import OP_UNKNOWN, validate_params
from jude_kernel.version import KERNEL_VERSION

UNITS_OP: Final = "units.to_mm"
FRAME_STEP: Final = "frame.apply"
BLOB_MISSING: Final = "BLOB_MISSING"
MESH: Final = "mesh"


class Stage(StrEnum):
    PREPARE = "prepare"  # units.to_mm and cleanup ops
    FRAME = "frame"
    DESIGN = "design"
    CLOSURE = "closure"


class StepStatus(StrEnum):
    OK = "ok"
    REJECTED = "rejected"
    FAILED = "failed"
    SKIPPED = "skipped"  # disabled op
    NOT_RUN = "not_run"  # after the stopping step


@dataclass(frozen=True)
class LoggedOp:
    """One DS-04 operation record, as replay needs it."""

    type: str
    op_version: int
    params: Mapping[str, Any]
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise KernelContractError(f"{self.type}: enabled must be a bool")
        if not isinstance(self.params, Mapping):
            raise KernelContractError(f"{self.type}: params must be a JSON object")


@dataclass(frozen=True)
class StepReport:
    stage: Stage
    index: int  # position within its stage list (prepare: 0 = units.to_mm)
    type: str
    op_version: int
    status: StepStatus
    cache_key: str | None = None
    cache_hit: bool = False
    output_sha: str | None = None
    reason_code: str | None = None
    report: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def as_json(self) -> dict[str, Any]:
        return {
            "stage": str(self.stage),
            "index": self.index,
            "type": self.type,
            "op_version": self.op_version,
            "status": str(self.status),
            "cache_key": self.cache_key,
            "cache_hit": self.cache_hit,
            "output_sha": self.output_sha,
            "reason_code": self.reason_code,
            "report": dict(self.report),
        }


@dataclass(frozen=True)
class ReplayResult:
    """``geometry`` is the positive when ``status`` is ok, else the last valid output."""

    status: OpStatus
    geometry: MeshArrays | None
    geometry_sha: str | None
    scan_prepared_sha: str | None
    steps: tuple[StepReport, ...]
    reason_code: str | None = None
    stopped_at: tuple[Stage, int] | None = None
    new_cache: Mapping[str, MeshArrays] = field(default_factory=lambda: MappingProxyType({}))


def cache_key(input_sha: str, op_type: str, op_version: int, params: Any) -> str:
    """FN-KRP-01.3 content-addressed key of one step."""
    doc = {
        "input_geometry_sha": input_sha,
        "type": op_type,
        "op_version": op_version,
        "params": params,
        "kernel_version": KERNEL_VERSION,
    }
    return hashlib.sha256(jcs_bytes(doc)).hexdigest()


def apply_frame(mesh: MeshArrays, frame: RigidTransform) -> MeshArrays:
    """scan_prepared (F_scan) in the confirmed frame: points moved, topology and tags kept."""
    if mesh.frame is not frame.from_frame:
        raise KernelContractError(
            f"frame: mesh is {mesh.frame}, transform starts at {frame.from_frame}"
        )
    return MeshArrays.create(
        frame.apply_points(mesh.V),
        mesh.F,
        frame=frame.to_frame,
        face_tags=mesh.face_tags,
        vertex_attrs=dict(mesh.vertex_attrs),
    )


class _Fold:
    """One replay run: the current geometry, the reports, and the cache entries produced."""

    def __init__(
        self, registry: Registry, cache: Mapping[str, MeshArrays], image_digest: str
    ) -> None:
        self.registry = registry
        self.cache = cache
        self.image_digest = image_digest
        self.steps: list[StepReport] = []
        self.new_cache: dict[str, MeshArrays] = {}
        self.stop: StepReport | None = None

    def _cached(self, key: str) -> MeshArrays | None:
        hit = self.cache.get(key)
        if hit is not None and (not isinstance(hit, MeshArrays) or hit.display_only):
            raise KernelContractError(f"cache entry {key}: a kernel MeshArrays is required")
        return hit

    def _report(
        self, stage: Stage, index: int, op: LoggedOp, status: StepStatus, **kw: Any
    ) -> None:
        step = StepReport(stage, index, op.type, op.op_version, status, **kw)
        self.steps.append(step)
        if status in (StepStatus.REJECTED, StepStatus.FAILED):
            self.stop = step

    def step(
        self, mesh: MeshArrays, sha: str, stage: Stage, index: int, op: LoggedOp
    ) -> tuple[MeshArrays, str]:
        if self.stop is not None:
            self._report(stage, index, op, StepStatus.NOT_RUN)
            return mesh, sha
        if not op.enabled:
            self._report(stage, index, op, StepStatus.SKIPPED)
            return mesh, sha
        spec = self.registry.get(op.type, op.op_version)
        if spec is None:
            self._report(stage, index, op, StepStatus.REJECTED, reason_code=OP_UNKNOWN)
            return mesh, sha
        if spec.input_kinds != (MESH,) or spec.output_kinds != (MESH,):
            raise KernelContractError(f"{op.type} v{op.op_version}: replay needs mesh -> mesh")
        reason = validate_params(spec, op.params)
        if reason is not None:
            self._report(stage, index, op, StepStatus.REJECTED, reason_code=reason)
            return mesh, sha
        key = cache_key(sha, op.type, op.op_version, op.params)
        hit = self._cached(key)
        if hit is not None:
            out_sha = mesh_geometry_sha256(hit)
            self._report(
                stage, index, op, StepStatus.OK, cache_key=key, cache_hit=True, output_sha=out_sha
            )
            return hit, out_sha
        result = run(
            self.registry,
            op.type,
            op.op_version,
            {MESH: mesh},
            op.params,
            validate=validate_params,
            image_digest=self.image_digest,
        )
        if result.status is not OpStatus.OK:
            status = (
                StepStatus.REJECTED if result.status is OpStatus.REJECTED else StepStatus.FAILED
            )
            self._report(
                stage,
                index,
                op,
                status,
                cache_key=key,
                reason_code=result.reason_code,
                report=result.report,
            )
            return mesh, sha
        out = result.outputs[MESH]
        out_sha = mesh_geometry_sha256(out)
        self.new_cache[key] = out
        self._report(
            stage, index, op, StepStatus.OK, cache_key=key, output_sha=out_sha, report=result.report
        )
        return out, out_sha

    def frame(self, mesh: MeshArrays, sha: str, frame: RigidTransform) -> tuple[MeshArrays, str]:
        op = LoggedOp(FRAME_STEP, 1, {"matrix": frame.as_row_major()})
        if self.stop is not None:
            self._report(Stage.FRAME, 0, op, StepStatus.NOT_RUN)
            return mesh, sha
        key = cache_key(sha, op.type, op.op_version, op.params)
        hit = self._cached(key)
        out = hit
        if out is None:
            out = apply_frame(mesh, frame)
            self.new_cache[key] = out
        out_sha = mesh_geometry_sha256(out)
        self._report(
            Stage.FRAME,
            0,
            op,
            StepStatus.OK,
            cache_key=key,
            cache_hit=hit is not None,
            output_sha=out_sha,
        )
        return out, out_sha


def replay(
    registry: Registry,
    *,
    original_sha: str,
    blobs: Mapping[str, MeshArrays],
    unit_op: LoggedOp,
    cleanup_ops: Sequence[LoggedOp],
    frame: RigidTransform,
    design_ops: Sequence[LoggedOp],
    closure: LoggedOp | None,
    cache: Mapping[str, MeshArrays],
    image_digest: str,
) -> ReplayResult:
    """FN-KRP-01: regenerate the positive from the recorded inputs (all explicit, no defaults)."""
    if unit_op.type != UNITS_OP or not unit_op.enabled:
        raise KernelContractError(f"stage 1 starts with an enabled {UNITS_OP} op")
    if frame.from_frame is not Frame.F_SCAN or frame.to_frame is not Frame.F_ANAT:
        raise KernelContractError("frame: the confirmed F_scan -> F_anat transform is required")
    if closure is not None and not closure.enabled:
        raise KernelContractError("closure: the pinned terminal op cannot be disabled (IDR-01)")

    original = blobs.get(original_sha)
    if original is None or mesh_geometry_sha256(original) != original_sha:
        detail = "not found" if original is None else "content does not match its sha"
        steps = (
            StepReport(
                Stage.PREPARE,
                0,
                unit_op.type,
                unit_op.op_version,
                StepStatus.NOT_RUN,
                report={"original": detail},
            ),
        )
        return ReplayResult(OpStatus.FAILED, None, None, None, steps, BLOB_MISSING)
    if original.frame is not Frame.F_FILE or original.display_only:
        raise KernelContractError("original: a kernel mesh in F_file is required")

    fold = _Fold(registry, cache, image_digest)
    mesh, sha = original, original_sha
    for i, op in enumerate([unit_op, *cleanup_ops]):
        mesh, sha = fold.step(mesh, sha, Stage.PREPARE, i, op)
    prepared_sha = sha if fold.stop is None else None
    mesh, sha = fold.frame(mesh, sha, frame)
    for i, op in enumerate(design_ops):
        mesh, sha = fold.step(mesh, sha, Stage.DESIGN, i, op)
    if closure is not None:
        mesh, sha = fold.step(mesh, sha, Stage.CLOSURE, 0, closure)

    new_cache = MappingProxyType(dict(fold.new_cache))
    if fold.stop is not None:
        stop = fold.stop
        status = OpStatus.REJECTED if stop.status is StepStatus.REJECTED else OpStatus.FAILED
        return ReplayResult(
            status,
            mesh,
            sha,
            prepared_sha,
            tuple(fold.steps),
            stop.reason_code,
            (stop.stage, stop.index),
            new_cache,
        )
    return ReplayResult(
        OpStatus.OK, mesh, sha, prepared_sha, tuple(fold.steps), new_cache=new_cache
    )
