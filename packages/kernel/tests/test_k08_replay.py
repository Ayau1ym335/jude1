"""UT-FN-KRP-01 / PT-FN-KRP-01: op-log replay engine (ALG-53; TSK-KRP-01-K).

Completion criteria:
- 100 regenerations of 10 reference designs give one geometry hash each (VER-07);
- disabling and then re-enabling an op returns the prior hash (TC-FR-053).

No shipped op exists yet; the ops below are synthetic. They use the registry contract every
FN-KOP op will use (``mesh`` -> ``mesh``, explicit params, no defaults). Their arithmetic is
ordinary float64 numpy, so any order or cache dependency in the engine would show as a hash
change.
"""

from collections.abc import Mapping
import importlib
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
import numpy as np
import pytest

from jude_kernel import KERNEL_VERSION
from jude_kernel.core import Frame, KernelContractError, MeshArrays, OpOutcome, OpSpec, Registry
from jude_kernel.core.result import OpStatus
from jude_kernel.k01_io import detect_bytes, from_soup, parse_stl
from jude_kernel.k03_frames.transform import RigidTransform
from jude_kernel.k08_replay import mesh_geometry_sha256
from jude_kernel.k08_replay.replay import (
    BLOB_MISSING,
    LoggedOp,
    ReplayResult,
    Stage,
    StepStatus,
    apply_frame,
    cache_key,
    replay,
)

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "T1"
DIGEST = "sha256:" + "cd" * 32


def kernel_op(fn: Any) -> Any:
    fn.__module__ = "jude_kernel.ops._test"  # the registry accepts kernel functions only
    return fn


def remesh(m: MeshArrays, v: Any, f: Any = None, frame: Frame | None = None) -> MeshArrays:
    return MeshArrays.create(v, m.F if f is None else f, frame=frame or m.frame)


CALLS: list[str] = []  # which ops actually ran (cache hits do not run)


@kernel_op
def units_to_mm(inputs: Mapping[str, MeshArrays], p: Mapping[str, Any]) -> OpOutcome:
    CALLS.append("units")
    m = inputs["mesh"]
    return OpOutcome.ok({"mesh": remesh(m, m.V * p["factor"], frame=Frame.F_SCAN)})


@kernel_op
def remove_faces(inputs: Mapping[str, MeshArrays], p: Mapping[str, Any]) -> OpOutcome:
    CALLS.append("remove")
    m = inputs["mesh"]
    keep = np.setdiff1d(np.arange(m.n_faces), np.asarray(p["face_ids"], dtype=np.int64))
    return OpOutcome.ok({"mesh": remesh(m, m.V, m.F[keep])}, {"removed": m.n_faces - keep.size})


@kernel_op
def translate(inputs: Mapping[str, MeshArrays], p: Mapping[str, Any]) -> OpOutcome:
    CALLS.append("translate")
    m = inputs["mesh"]
    return OpOutcome.ok({"mesh": remesh(m, m.V + np.asarray(p["offset_mm"]))})


@kernel_op
def inflate(inputs: Mapping[str, MeshArrays], p: Mapping[str, Any]) -> OpOutcome:
    """Move every vertex radially from the centroid: sums, sqrt and division (order matters)."""
    CALLS.append("inflate")
    m = inputs["mesh"]
    d = m.V - m.V.mean(axis=0)
    unit = d / np.linalg.norm(d, axis=1)[:, None]
    return OpOutcome.ok({"mesh": remesh(m, m.V + p["magnitude_mm"] * unit)})


@kernel_op
def clamp_base(inputs: Mapping[str, MeshArrays], p: Mapping[str, Any]) -> OpOutcome:
    """Stand-in for the closure: flatten everything below the base plane onto it."""
    CALLS.append("closure")
    m = inputs["mesh"]
    v = m.V.copy()
    v[:, 2] = np.maximum(v[:, 2], p["base_z_mm"])
    return OpOutcome.ok({"mesh": remesh(m, v)})


@kernel_op
def always_reject(inputs: Mapping[str, MeshArrays], p: Mapping[str, Any]) -> OpOutcome:
    CALLS.append("reject")
    return OpOutcome.rejected("SELF_INTERSECTION_CREATED", {"pairs": 1})


@kernel_op
def raises(inputs: Mapping[str, MeshArrays], p: Mapping[str, Any]) -> OpOutcome:
    raise ZeroDivisionError


@kernel_op
def other_kinds(inputs: Mapping[str, MeshArrays], p: Mapping[str, Any]) -> OpOutcome:
    return OpOutcome.ok({"out": inputs["src"]})


def schema(**props: Any) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": sorted(props),
            "properties": props}  # fmt: skip


NUM = {"type": "number"}
EMPTY = schema()


def spec(t: str, fn: Any, sch: dict[str, Any], v: int = 1, kinds: str = "mesh") -> OpSpec:
    return OpSpec(type=t, version=v, fn=fn, params_schema=sch, input_kinds=(kinds,),
                  output_kinds=(kinds if kinds == "mesh" else "out",), topology_preserving=True,
                  guard=False, idempotent=False)  # fmt: skip


REG = Registry([
    spec("units.to_mm", units_to_mm, schema(factor={"type": "number", "exclusiveMinimum": 0})),
    spec("test.remove_faces", remove_faces,
         schema(face_ids={"type": "array", "items": {"type": "integer", "minimum": 0}})),
    spec("test.translate", translate,
         schema(offset_mm={"type": "array", "items": NUM, "minItems": 3, "maxItems": 3})),
    spec("test.inflate", inflate, schema(magnitude_mm=NUM)),
    spec("test.inflate", inflate, schema(magnitude_mm=NUM), v=2),  # same code, new op_version
    spec("test.closure", clamp_base, schema(base_z_mm=NUM)),
    spec("test.reject", always_reject, EMPTY),
    spec("test.raise", raises, EMPTY),
    spec("test.other", other_kinds, EMPTY, kinds="src"),
])  # fmt: skip


def load(name: str) -> MeshArrays:
    data = (FIXTURES / name / "mesh.stl").read_bytes()
    soup = parse_stl(data, detect_bytes(data).format, max_faces=10**6).soup  # type: ignore[arg-type]
    built = from_soup(soup, max_faces=10**6)
    assert built.mesh is not None
    return built.mesh


MESHES = {n: load(n) for n in ("icosphere_s4_r75", "ellipsoid_s4", "ellipsoid_asym_s4",
                               "torus_R60_r20")}  # fmt: skip
SHAS = {n: mesh_geometry_sha256(m) for n, m in MESHES.items()}
BLOBS = {SHAS[n]: m for n, m in MESHES.items()}
COS, SIN = np.cos(0.3), np.sin(0.3)
FRAME = RigidTransform.create(
    [[COS, -SIN, 0, 1.5], [SIN, COS, 0, -2.0], [0, 0, 1, 0.25], [0, 0, 0, 1]],
    from_frame=Frame.F_SCAN, to_frame=Frame.F_ANAT,
)  # fmt: skip


def op(t: str, enabled: bool = True, v: int = 1, **params: Any) -> LoggedOp:
    return LoggedOp(t, v, params, enabled)


UNITS = op("units.to_mm", factor=1.0)
CLOSURE = op("test.closure", base_z_mm=-20.0)

# Ten reference designs: (fixture, unit op, cleanup ops, design ops, closure).
DESIGNS: list[tuple[str, LoggedOp, list[LoggedOp], list[LoggedOp], LoggedOp | None]] = [
    ("icosphere_s4_r75", UNITS, [], [], None),
    ("icosphere_s4_r75", UNITS, [], [op("test.inflate", magnitude_mm=2.5)], CLOSURE),
    ("icosphere_s4_r75", op("units.to_mm", factor=10.0), [op("test.remove_faces", face_ids=[0, 7])],
     [op("test.translate", offset_mm=[0.1, -0.2, 0.3])], None),
    ("ellipsoid_s4", UNITS, [], [op("test.inflate", magnitude_mm=1.0),
                                 op("test.inflate", magnitude_mm=-0.75)], CLOSURE),
    ("ellipsoid_s4", UNITS, [op("test.remove_faces", face_ids=[3])],
     [op("test.inflate", v=2, magnitude_mm=0.3), op("test.translate", offset_mm=[1e-3, 0, 0])],
     CLOSURE),
    ("ellipsoid_asym_s4", UNITS, [], [op("test.translate", offset_mm=[5.0, 5.0, 5.0]),
                                      op("test.inflate", magnitude_mm=4.0)], None),
    ("ellipsoid_asym_s4", op("units.to_mm", factor=25.4), [],
     [op("test.inflate", magnitude_mm=0.1, enabled=False), op("test.inflate", magnitude_mm=0.2)],
     op("test.closure", base_z_mm=0.0)),
    ("torus_R60_r20", UNITS, [], [op("test.inflate", magnitude_mm=3.0)], CLOSURE),
    ("torus_R60_r20", UNITS, [op("test.remove_faces", face_ids=list(range(0, 40, 3)))],
     [op("test.translate", offset_mm=[0.0, 0.0, -1.0]), op("test.inflate", magnitude_mm=0.5),
      op("test.translate", offset_mm=[0.0, 0.0, 1.0])], CLOSURE),
    ("torus_R60_r20", op("units.to_mm", factor=0.5), [],
     [op("test.inflate", magnitude_mm=x) for x in (0.1, 0.2, 0.3, 0.4)], None),
]  # fmt: skip


def go(
    design: tuple[str, LoggedOp, list[LoggedOp], list[LoggedOp], LoggedOp | None],
    cache: Mapping[str, MeshArrays] | None = None,
    **over: Any,
) -> ReplayResult:
    name, units, cleanup, ops, closure = design
    kw: dict[str, Any] = dict(original_sha=SHAS[name], blobs=BLOBS, unit_op=units,
                              cleanup_ops=cleanup, frame=FRAME, design_ops=ops, closure=closure,
                              cache=cache or {}, image_digest=DIGEST)  # fmt: skip
    kw.update(over)
    return replay(REG, **kw)


def design_with(ops: list[LoggedOp], closure: LoggedOp | None = None) -> Any:
    return ("icosphere_s4_r75", UNITS, [], ops, closure)


# --- completion criteria -------------------------------------------------------------------------


def test_reference_designs_replay_ok_and_are_distinct() -> None:
    shas = []
    for d in DESIGNS:
        r = go(d)
        assert r.status is OpStatus.OK and r.geometry is not None, r.reason_code
        assert r.geometry_sha == mesh_geometry_sha256(r.geometry)
        assert r.geometry.frame is Frame.F_ANAT
        shas.append(r.geometry_sha)
    assert len(set(shas)) == len(DESIGNS)


def test_three_regenerations_give_one_hash_each() -> None:  # unit-stage cut of the criterion
    for d in DESIGNS:
        assert len({go(d).geometry_sha for _ in range(3)}) == 1


@pytest.mark.determinism
def test_completion_criterion_100_regenerations_of_10_designs_give_one_hash_each() -> None:
    for d in DESIGNS:
        shas = set()
        cache: dict[str, MeshArrays] = {}
        for i in range(100):
            r = go(d, cache if i % 2 else None)  # alternate cold and warm cache
            cache.update(r.new_cache)
            shas.add(r.geometry_sha)
        assert len(shas) == 1, d[0]


def test_completion_criterion_disable_then_re_enable_returns_the_prior_hash() -> None:
    ops = [op("test.inflate", magnitude_mm=2.0), op("test.translate", offset_mm=[1.0, 0, 0])]
    before = go(design_with(ops, CLOSURE))
    disabled = [ops[0], op("test.translate", enabled=False, offset_mm=[1.0, 0, 0])]
    off = go(design_with(disabled, CLOSURE))
    again = go(design_with(ops, CLOSURE))
    assert off.geometry_sha != before.geometry_sha
    assert again.geometry_sha == before.geometry_sha
    design = [s.status for s in off.steps if s.stage is Stage.DESIGN]
    assert design == [StepStatus.OK, StepStatus.SKIPPED]
    # a design whose only op is disabled equals the design without it
    only = go(design_with([op("test.inflate", enabled=False, magnitude_mm=2.0)]))
    assert only.geometry_sha == go(design_with([])).geometry_sha


# --- stages, frame, closure ----------------------------------------------------------------------


def test_stage_one_and_frame_produce_scan_prepared_in_f_anat() -> None:
    m = MESHES["icosphere_s4_r75"]
    r = go(design_with([]))
    assert [s.stage for s in r.steps] == [Stage.PREPARE, Stage.FRAME]
    prepared = MeshArrays.create(m.V * 1.0, m.F, frame=Frame.F_SCAN)
    assert r.scan_prepared_sha == mesh_geometry_sha256(prepared)
    assert r.geometry is not None
    assert np.array_equal(r.geometry.V, FRAME.apply_points(m.V))
    assert r.steps[1].output_sha == r.geometry_sha


def test_cleanup_ops_run_in_order_before_the_frame() -> None:
    twice = [op("test.remove_faces", face_ids=[0]), op("test.remove_faces", face_ids=[0])]
    r = go(("icosphere_s4_r75", UNITS, twice, [], None))
    assert r.geometry is not None and r.geometry.n_faces == MESHES["icosphere_s4_r75"].n_faces - 2
    order = [(s.stage, s.index) for s in r.steps]
    assert order == [(Stage.PREPARE, 0), (Stage.PREPARE, 1), (Stage.PREPARE, 2), (Stage.FRAME, 0)]


def test_closure_is_evaluated_last_whatever_the_design_ops() -> None:
    ops = [op("test.translate", offset_mm=[0, 0, -30.0])]
    r = go(design_with(ops, op("test.closure", base_z_mm=-20.0)))
    assert r.geometry is not None and r.geometry.V[:, 2].min() == -20.0
    assert r.steps[-1].stage is Stage.CLOSURE and r.steps[-1].type == "test.closure"


def test_op_versions_are_distinct_registry_entries() -> None:
    v1 = go(design_with([op("test.inflate", magnitude_mm=1.0)]))
    v2 = go(design_with([op("test.inflate", v=2, magnitude_mm=1.0)]))
    assert v1.geometry_sha == v2.geometry_sha  # same code here...
    assert v1.steps[-1].cache_key != v2.steps[-1].cache_key  # ...but never the same cache entry


# --- per-op cache --------------------------------------------------------------------------------


def test_cache_key_is_the_documented_jcs_document() -> None:
    import hashlib
    import json

    key = cache_key("ab" * 32, "test.inflate", 1, {"magnitude_mm": 2.5})
    doc = {"input_geometry_sha": "ab" * 32, "kernel_version": KERNEL_VERSION, "op_version": 1,
           "params": {"magnitude_mm": 2.5}, "type": "test.inflate"}  # fmt: skip
    canonical = json.dumps(doc, separators=(",", ":"), sort_keys=True).encode()
    assert key == hashlib.sha256(canonical).hexdigest()
    # every field is part of the key
    assert cache_key("ab" * 32, "test.inflate", 2, {"magnitude_mm": 2.5}) != key
    assert cache_key("ac" * 32, "test.inflate", 1, {"magnitude_mm": 2.5}) != key
    assert cache_key("ab" * 32, "test.inflate", 1, {"magnitude_mm": 2.6}) != key


def test_a_cache_entry_from_another_kernel_version_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("jude_kernel.k08_replay.replay")  # the function shadows it

    d = design_with([op("test.inflate", magnitude_mm=1.0)])
    old = go(d).new_cache
    monkeypatch.setattr(module, "KERNEL_VERSION", "0.2.0")
    r = go(d, old)
    assert not any(s.cache_hit for s in r.steps)
    assert set(r.new_cache).isdisjoint(old)


def test_editing_op_k_recomputes_only_k_to_n() -> None:
    ops = [op("test.inflate", magnitude_mm=x) for x in (1.0, 2.0, 3.0, 4.0)]
    first = go(design_with(ops))
    edited = [*ops[:2], op("test.inflate", magnitude_mm=2.5), ops[3]]
    CALLS.clear()
    r = go(design_with(edited), first.new_cache)
    assert CALLS == ["inflate", "inflate"]  # ops 3 and 4 of 4; units, frame, 1, 2 were hits
    assert [s.cache_hit for s in r.steps] == [True, True, True, True, False, False]


def test_only_ok_outputs_are_cached_and_hits_are_reported() -> None:
    d = design_with([op("test.inflate", magnitude_mm=1.0), op("test.reject")])
    r = go(d)
    assert len(r.new_cache) == 3  # units, frame, inflate; never the rejected step
    warm = go(d, r.new_cache)
    assert warm.new_cache == {}
    assert (warm.status, warm.geometry_sha) == (r.status, r.geometry_sha)


def test_a_bad_cache_entry_is_a_caller_bug() -> None:
    d = design_with([])
    key = go(d).steps[0].cache_key
    assert key is not None
    m = MESHES["icosphere_s4_r75"]
    lod = MeshArrays.create(m.V, m.F, frame=Frame.F_SCAN, display_only=True)
    with pytest.raises(KernelContractError, match="cache entry"):
        go(d, {key: lod})
    frame_key = go(d).steps[1].cache_key
    assert frame_key is not None
    with pytest.raises(KernelContractError, match="cache entry"):
        go(d, {frame_key: "not a mesh"})  # type: ignore[dict-item]


# --- failure handling (SAF-09) -------------------------------------------------------------------


def test_first_rejection_stops_and_returns_the_last_valid_output() -> None:
    ops = [op("test.inflate", magnitude_mm=1.0), op("test.reject"),
           op("test.inflate", magnitude_mm=5.0)]  # fmt: skip
    r = go(design_with(ops, CLOSURE))
    valid = go(design_with(ops[:1]))
    assert (r.status, r.reason_code, r.stopped_at) == (
        OpStatus.REJECTED,
        "SELF_INTERSECTION_CREATED",
        (Stage.DESIGN, 1),
    )
    assert r.geometry_sha == valid.geometry_sha  # the output of the step before
    statuses = [s.status for s in r.steps]
    assert statuses[-3:] == [StepStatus.REJECTED, StepStatus.NOT_RUN, StepStatus.NOT_RUN]
    assert r.steps[-3].report == {"pairs": 1}


def test_failed_op_stops_as_failed() -> None:
    r = go(design_with([op("test.raise")]))
    assert (r.status, r.reason_code, r.stopped_at) == (OpStatus.FAILED, "KERNEL_EXCEPTION",
                                                       (Stage.DESIGN, 0))  # fmt: skip


def test_a_stage_one_rejection_skips_the_frame_and_design() -> None:
    r = go(("icosphere_s4_r75", UNITS, [op("test.reject")], [op("test.inflate", magnitude_mm=1)],
            CLOSURE))  # fmt: skip
    assert r.stopped_at == (Stage.PREPARE, 1) and r.scan_prepared_sha is None
    assert [s.status for s in r.steps][2:] == [StepStatus.NOT_RUN] * 3
    assert r.geometry is not None and r.geometry.frame is Frame.F_SCAN  # last valid: after units


@pytest.mark.parametrize(
    ("bad", "code"),
    [
        (op("test.nope"), "OP_UNKNOWN"),
        (op("test.inflate", v=9, magnitude_mm=1.0), "OP_UNKNOWN"),
        (op("test.inflate"), "PARAM_NOT_SET"),
        (op("test.inflate", magnitude_mm="2"), "PARAM_INVALID"),
        (op("test.inflate", magnitude_mm=1.0, extra=1), "PARAM_INVALID"),
    ],
)
def test_unknown_ops_and_invalid_params_are_rejected_before_running(
    bad: LoggedOp, code: str
) -> None:
    CALLS.clear()
    r = go(design_with([bad]))
    assert (r.status, r.reason_code) == (OpStatus.REJECTED, code)
    assert "inflate" not in CALLS and r.steps[-1].cache_key is None


def test_blob_missing() -> None:  # one negative test per error code
    missing = go(design_with([]), original_sha="00" * 32)
    assert (missing.status, missing.reason_code) == (OpStatus.FAILED, BLOB_MISSING)
    assert missing.geometry is None
    assert missing.steps[0].report == {"original": "not found"}
    swapped = {SHAS["icosphere_s4_r75"]: MESHES["torus_R60_r20"]}
    tampered = go(design_with([]), blobs=swapped)
    assert tampered.reason_code == BLOB_MISSING
    assert tampered.steps[0].report == {"original": "content does not match its sha"}


@pytest.mark.parametrize(
    "over",
    [
        {"unit_op": op("test.translate", offset_mm=[0, 0, 0])},
        {"unit_op": op("units.to_mm", enabled=False, factor=1.0)},
        {"closure": op("test.closure", enabled=False, base_z_mm=0.0)},
        {"frame": RigidTransform.identity(Frame.F_SCAN)},
        {"design_ops": [op("test.other")]},
    ],
)
def test_contract(over: dict[str, Any]) -> None:
    with pytest.raises(KernelContractError):
        go(design_with([]), **over)


def test_original_must_be_a_file_frame_kernel_mesh() -> None:
    m = MESHES["icosphere_s4_r75"]
    scan = MeshArrays.create(m.V, m.F, frame=Frame.F_SCAN)
    sha = mesh_geometry_sha256(scan)
    with pytest.raises(KernelContractError, match="F_file"):
        go(design_with([]), original_sha=sha, blobs={sha: scan})


def test_logged_op_contract() -> None:
    with pytest.raises(KernelContractError):
        LoggedOp("test.inflate", 1, {}, enabled=1)  # type: ignore[arg-type]
    with pytest.raises(KernelContractError):
        LoggedOp("test.inflate", 1, [])  # type: ignore[arg-type]


def test_step_report_json() -> None:
    step = go(design_with([])).steps[0]
    doc = step.as_json()
    assert doc["stage"] == "prepare" and doc["status"] == "ok" and doc["type"] == "units.to_mm"
    assert doc["output_sha"] == step.output_sha and doc["report"] == {}


# --- properties ----------------------------------------------------------------------------------

op_strategy = st.one_of(
    st.builds(lambda x, e: op("test.inflate", e, magnitude_mm=x),
              st.sampled_from([-1.0, 0.5, 2.0]), st.booleans()),
    st.builds(lambda x, e: op("test.translate", e, offset_mm=[x, -x, 0.0]),
              st.sampled_from([0.25, 3.0]), st.booleans()),
    st.just(op("test.reject")),
)  # fmt: skip


@settings(max_examples=60, deadline=None)
@given(st.lists(op_strategy, max_size=5), st.data())
def test_property_replay_is_independent_of_cache_state(ops: list[LoggedOp], data: Any) -> None:
    d = design_with(ops, CLOSURE)
    cold = go(d)
    keys = sorted(cold.new_cache)
    subset = data.draw(st.lists(st.sampled_from(keys), unique=True) if keys else st.just([]))
    warm = go(d, {k: cold.new_cache[k] for k in subset})
    assert (warm.status, warm.geometry_sha, warm.reason_code, warm.stopped_at) == (
        cold.status,
        cold.geometry_sha,
        cold.reason_code,
        cold.stopped_at,
    )
    assert [s.output_sha for s in warm.steps] == [s.output_sha for s in cold.steps]
    # disabled ops are skipped exactly as if they were not there
    enabled = [o for o in ops if o.enabled]
    assert go(design_with(enabled, CLOSURE)).geometry_sha == cold.geometry_sha


def test_apply_frame_moves_points_and_keeps_topology_tags_and_attributes() -> None:
    m = MESHES["icosphere_s4_r75"]
    tags = np.full(m.n_faces, 1, dtype=np.uint8)
    attr = np.arange(m.n_vertices, dtype=np.float64)
    scan = MeshArrays.create(m.V, m.F, frame=Frame.F_SCAN, face_tags=tags,
                             vertex_attrs={"curvature": attr})  # fmt: skip
    out = apply_frame(scan, FRAME)
    assert out.frame is Frame.F_ANAT and np.array_equal(out.V, FRAME.apply_points(m.V))
    assert np.array_equal(out.F, m.F) and out.face_tags is not None
    assert np.array_equal(out.face_tags, tags)
    assert np.array_equal(out.vertex_attrs["curvature"], attr)
    with pytest.raises(KernelContractError, match="frame"):
        apply_frame(m, FRAME)  # F_file is not where the confirmed frame starts
