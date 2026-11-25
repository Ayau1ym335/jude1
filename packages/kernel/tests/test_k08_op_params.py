"""UT-FN-KRP-04 / PT-FN-KRP-04: op registry and parameter validation (ALG-61; TSK-KRP-04-K).

Completion criterion: the schema test proves there are no defaults; a missing magnitude returns
PARAM_NOT_SET. The test op schemas below are fixtures only. The shipped op schemas are
registered by each op's TT-K task, and the meta-test and the snapshot cover them from then on.
"""

from collections.abc import Mapping
import json
import math
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
import numpy as np
import pytest

from jude_kernel.core import REGISTRY, Frame, MeshArrays, OpOutcome, OpSpec, OpStatus, Registry, run
from jude_kernel.k08_replay import (
    OP_UNKNOWN,
    PARAM_INVALID,
    PARAM_NOT_SET,
    check_request,
    registry_fingerprint,
    registry_problems,
    schema_problems,
    validate_against,
    validate_params,
)

SNAPSHOT = Path(__file__).with_name("registry_snapshot.json")
MESH = MeshArrays.create(
    np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64),
    np.array([[0, 1, 2]], dtype=np.int32),
    frame=Frame.F_SCAN,
)


def _op(inputs: Mapping[str, MeshArrays], params: Mapping[str, Any]) -> OpOutcome:
    return OpOutcome.ok({"out": inputs["src"]})


_op.__module__ = "jude_kernel.ops._test"  # the registry accepts kernel functions only

# A zone-like op: every value explicit, technical bounds only (radius > 0, transition >= 0).
ZONE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "magnitude_mm", "radius_mm", "transition_mm", "center"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "magnitude_mm": {"type": "number"},
        "radius_mm": {"type": "number", "exclusiveMinimum": 0},
        "transition_mm": {"type": "number", "minimum": 0},
        "center": {
            "type": "object",
            "additionalProperties": False,
            "required": ["x_mm", "y_mm"],
            "properties": {"x_mm": {"type": "number"}, "y_mm": {"type": "number"}},
        },
    },
}
SMOOTH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["iterations"],
    "properties": {"iterations": {"type": "integer", "minimum": 1}},
}
VALID = {"name": "Зона лобная", "magnitude_mm": 2.5, "radius_mm": 30.0, "transition_mm": 0.0,
         "center": {"x_mm": 1.0, "y_mm": -2.0}}  # fmt: skip


def spec(schema: Mapping[str, Any], type_: str = "test.zone", version: int = 1) -> OpSpec:
    return OpSpec(
        type=type_, version=version, fn=_op, params_schema=schema, input_kinds=("src",),
        output_kinds=("out",), topology_preserving=True, guard=False, idempotent=True,
    )  # fmt: skip


ZONE = spec(ZONE_SCHEMA)
TEST_REGISTRY = Registry([ZONE, spec(SMOOTH_SCHEMA, "test.smooth", 2)])


# --- completion criterion ---------------------------------------------------------------------


def test_completion_criterion_schema_test_proves_no_defaults() -> None:
    assert registry_problems(REGISTRY) == {}  # the shipped registry
    assert registry_problems(TEST_REGISTRY) == {}
    seeded = json.loads(json.dumps(ZONE_SCHEMA))
    seeded["properties"]["magnitude_mm"]["default"] = 2.0  # a clinical value, defaulted
    assert schema_problems(seeded) == ["/properties/magnitude_mm: 'default' is forbidden "
                                       "(DEC-029, INV-12)"]  # fmt: skip
    nested = json.loads(json.dumps(ZONE_SCHEMA))
    nested["properties"]["center"]["properties"]["x_mm"]["default"] = 0
    assert any("default" in p for p in schema_problems(nested))
    root = {**ZONE_SCHEMA, "default": {}}
    assert any(p.startswith("/: 'default'") for p in schema_problems(root))


def test_completion_criterion_missing_magnitude_is_param_not_set() -> None:
    params = {k: v for k, v in VALID.items() if k != "magnitude_mm"}
    check = validate_against(ZONE, params)
    assert (check.reason, check.pointer) == (PARAM_NOT_SET, "/magnitude_mm")
    assert validate_params(ZONE, params) == PARAM_NOT_SET
    # the kernel runner refuses the op instead of running it with an implied value
    r = run(TEST_REGISTRY, "test.zone", 1, {"src": MESH}, params, validate=validate_params,
            image_digest="sha256:" + "ab" * 32)  # fmt: skip
    assert (r.status, r.reason_code) == (OpStatus.REJECTED, PARAM_NOT_SET)


# --- request validation ---------------------------------------------------------------------------


def test_valid_params_come_back_as_a_private_copy() -> None:
    params = json.loads(json.dumps(VALID))
    check = check_request(TEST_REGISTRY, "test.zone", 1, params)
    assert check.reason is None and check.params is not None and check.params == params
    assert check.params is not params and check.params["center"] is not params["center"]


@pytest.mark.parametrize(
    ("op_type", "version"), [("test.zone", 2), ("nope", 1), ("test.smooth", 1)]
)
def test_unknown_op_or_version(op_type: str, version: int) -> None:
    assert check_request(TEST_REGISTRY, op_type, version, VALID).reason == OP_UNKNOWN


@pytest.mark.parametrize("key", ZONE_SCHEMA["required"])
def test_each_required_key_missing_is_param_not_set(key: str) -> None:
    params = {k: v for k, v in VALID.items() if k != key}
    check = validate_against(ZONE, params)
    assert (check.reason, check.pointer) == (PARAM_NOT_SET, f"/{key}")


def test_nested_missing_key_points_into_the_object() -> None:
    check = validate_against(ZONE, {**VALID, "center": {"x_mm": 1.0}})
    assert (check.reason, check.pointer) == (PARAM_NOT_SET, "/center/y_mm")


@pytest.mark.parametrize(
    ("change", "pointer"),
    [
        ({"radius_mm": 0.0}, "/radius_mm"),  # structural bound: radius > 0
        ({"radius_mm": -1.0}, "/radius_mm"),
        ({"transition_mm": -0.5}, "/transition_mm"),  # transition >= 0
        ({"magnitude_mm": "2.5"}, "/magnitude_mm"),  # wrong type
        ({"magnitude_mm": True}, "/magnitude_mm"),  # a bool is not a number in JSON
        ({"magnitude_mm": math.nan}, "/magnitude_mm"),
        ({"magnitude_mm": math.inf}, "/magnitude_mm"),
        ({"radius_mm": -math.inf}, "/radius_mm"),
        ({"magnitude_mm": 2**53 + 1}, "/magnitude_mm"),
        ({"name": ""}, "/name"),
        ({"extra_mm": 1.0}, ""),  # unknown key (additionalProperties false, at the root)
        ({"center": {"x_mm": 1.0, "y_mm": 2.0, "z_mm": 3.0}}, "/center"),
    ],
)
def test_param_invalid(change: dict[str, Any], pointer: str) -> None:
    check = validate_against(ZONE, {**VALID, **change})
    assert (check.reason, check.pointer) == (PARAM_INVALID, pointer), check.detail


@pytest.mark.parametrize("iterations", [0, -3, 1.5, "1"])
def test_integer_bounds(iterations: Any) -> None:
    smooth = TEST_REGISTRY.get("test.smooth", 2)
    assert smooth is not None
    assert validate_params(smooth, {"iterations": iterations}) == PARAM_INVALID
    assert validate_params(smooth, {"iterations": 1}) is None


def test_not_set_wins_and_the_answer_is_deterministic() -> None:
    params = {"radius_mm": -1.0, "extra": 1, "name": ""}
    first = validate_against(ZONE, params)
    assert first.reason == PARAM_NOT_SET and first.pointer == "/center"  # first missing key
    assert all(validate_against(ZONE, dict(reversed(params.items()))) == first for _ in range(5))


def test_params_must_be_an_object() -> None:
    assert validate_params(ZONE, [VALID]) == PARAM_INVALID  # type: ignore[arg-type]


@settings(max_examples=200, deadline=None)
@given(
    magnitude=st.floats(allow_nan=False, allow_infinity=False),
    radius=st.floats(min_value=0, allow_nan=False, allow_infinity=False, exclude_min=True),
    transition=st.floats(min_value=0, allow_nan=False, allow_infinity=False),
)
def test_property_any_finite_value_inside_the_structural_bounds_is_valid(
    magnitude: float, radius: float, transition: float
) -> None:
    params = {**VALID, "magnitude_mm": magnitude, "radius_mm": radius, "transition_mm": transition}
    assert validate_params(ZONE, params) is None


# --- schema rules ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutate", "expect"),
    [
        (lambda s: s.pop("additionalProperties"), "/: additionalProperties must be false"),
        (lambda s: s["required"].remove("transition_mm"), "every property must be required"),
        (lambda s: s["properties"]["center"].update(additionalProperties=True),
         "/properties/center: additionalProperties must be false"),
        (lambda s: s.update(type="array"), "root: params must be an object schema"),
        (lambda s: s["properties"].update(ext={"$ref": "https://example.org/x.json"}),
         "only local $ref"),
        (lambda s: s.update(type="objekt"), "not a valid JSON Schema 2020-12 document"),
    ],
)  # fmt: skip
def test_schema_rules(mutate: Any, expect: str) -> None:
    schema = json.loads(json.dumps(ZONE_SCHEMA))
    mutate(schema)
    problems = schema_problems(schema)
    assert any(expect in p for p in problems), problems


def test_a_parameter_named_default_is_allowed() -> None:
    # "default" as a *parameter name* under "properties" is not the JSON Schema keyword.
    schema = {"type": "object", "additionalProperties": False, "required": ["default"],
              "properties": {"default": {"type": "boolean"}}}  # fmt: skip
    assert schema_problems(schema) == []


def test_registry_problems_name_the_op_version() -> None:
    bad = Registry([spec({**SMOOTH_SCHEMA, "default": {"iterations": 3}}, "test.smooth", 1)])
    assert list(registry_problems(bad)) == ["test.smooth v1"]


# --- registry snapshot ----------------------------------------------------------------------------


def test_registry_snapshot_no_silent_schema_change_or_removal() -> None:
    """A registered (type, version) keeps its schema forever; changing it needs a new version.

    Old versions stay registered so saved designs can be replayed (ALG-61). Adding an op version
    means adding its fingerprint to registry_snapshot.json in the same change.
    """
    committed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    current = {
        (e["type"], e["version"]): e["schema_sha256"] for e in registry_fingerprint(REGISTRY)
    }
    for entry in committed["ops"]:
        key = (entry["type"], entry["version"])
        assert key in current, f"{key} was removed: saved designs could no longer replay"
        assert current[key] == entry["schema_sha256"], f"{key} changed schema without a new version"
    assert len(current) == len(committed["ops"]), "new op version: add it to registry_snapshot.json"


def test_fingerprint_is_sorted_and_tracks_the_schema() -> None:
    fp = registry_fingerprint(TEST_REGISTRY)
    assert [(e["type"], e["version"]) for e in fp] == [("test.smooth", 2), ("test.zone", 1)]
    changed = Registry([spec({**ZONE_SCHEMA, "minProperties": 5})])
    assert registry_fingerprint(changed)[0]["schema_sha256"] != fp[1]["schema_sha256"]
