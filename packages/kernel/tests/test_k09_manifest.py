"""UT-FN-KEX-01 / PT-FN-KEX-01: build export manifest (ALG-52; TSK-KEX-01-K).

Completion criteria:
- the manifest validates against the published schema;
- the STL hash in the manifest equals the file hash;
- an effect block is present for every op.

The data are synthetic test values, not clinical values: the categories, names and
magnitudes are placeholders.
"""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
import jsonschema
import numpy as np
import pytest

from jude_kernel import KERNEL_VERSION
from jude_kernel.core import Frame, KernelContractError, MeshArrays
from jude_kernel.k01_io import stl_header, write_binary_stl
from jude_kernel.k08_replay import parse_json
from jude_kernel.k09_export import (
    DEVICE_SIDE,
    MANIFEST_INCOMPLETE,
    MANIFEST_SCHEMA,
    MANIFEST_SCHEMA_ID,
    build_manifest,
)

PUBLISHED = Path(__file__).resolve().parents[1] / "schemas" / "jude-manifest-0.1.schema.json"
SHA_A, SHA_B, SHA_C = "a" * 64, "b" * 64, "c" * 64
MESH = MeshArrays.create(
    np.array([[0.0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]]),
    np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]),
    frame=Frame.F_EXPORT,
)
STL = write_binary_stl(MESH, header=stl_header("0.1.0", "J-0123ABCD", 2)).data
EXPORT_FRAME = [0.0, -1, 0, 5, 1, 0, 0, -3, 0, 0, 1, 12.5, 0, 0, 0, 1]


def ops() -> list[dict[str, Any]]:
    return [
        {"seq": 1, "type": "zone.relief", "op_version": 1, "category": "test-category-a",
         "name": "Зона 1", "params": {"magnitude_mm": 2.5}, "positive_surface": "outward"},
        {"seq": 2, "type": "offset.normal", "op_version": 1, "category": None, "name": None,
         "params": {"offset_mm": -0.5, "purpose": "test"}, "positive_surface": "inward"},
        {"seq": 3, "type": "closure.base", "op_version": 1, "category": None, "name": None,
         "params": {"plane": "test"}, "positive_surface": "unchanged"},
    ]  # fmt: skip


def inputs(**over: Any) -> dict[str, Any]:
    kw: dict[str, Any] = {
        "case_id": "J-0123ABCD",
        "design_version_id": "6f1c0a52-8d0e-4c1f-9a51-0f6f8f0b1a11",
        "design_version_number": 2,
        "stl_name": "J-0123ABCD_v2.stl",
        "stl": STL,
        "frame_matrix": EXPORT_FRAME,
        "frame_definition_ref": "export-rule/test",
        "config_version": 7,
        "source_scan_sha256": SHA_A,
        "operations": ops(),
        "template_ref": None,
        "approval": {"approval_id": "ap-1", "geometry_sha256": SHA_B, "params_sha256": SHA_C,
                     "approved_at_utc": "2026-11-28T09:00:00Z"},
        "reimport_check": {"passed": True, "triangle_count_equal": True,
                           "max_vertex_deviation_mm": 0.0, "tolerance_mm": 1e-4},
        "index_values": [{"name": "CI", "value": 81.25, "unit": "%",
                          "definition_id": "def-ci-test", "definition_version": 3}],
        "software_build": "jude 0.1.0+test",
        "created_at_utc": "2026-11-28T09:05:00Z",
        "intended_use_statement": "Test statement (SAF-01 text comes from configuration).",
    }  # fmt: skip
    kw.update(over)
    return kw


# --- completion criteria -------------------------------------------------------------------------


def test_completion_criterion_manifest_validates_against_the_published_schema() -> None:
    r = build_manifest(**inputs())
    assert r.reason_code is None and r.document is not None and r.data is not None
    published = json.loads(PUBLISHED.read_text(encoding="utf-8"))
    assert published == MANIFEST_SCHEMA  # the published file is the kernel's schema
    jsonschema.Draft202012Validator.check_schema(published)
    jsonschema.validate(json.loads(r.data), published, cls=jsonschema.Draft202012Validator)
    assert r.document["schema"] == MANIFEST_SCHEMA_ID


def test_completion_criterion_stl_hash_equals_the_file_hash() -> None:
    r = build_manifest(**inputs())
    assert r.document is not None
    (entry,) = r.document["files"]
    assert entry["sha256"] == hashlib.sha256(STL).hexdigest()
    assert (entry["size_bytes"], entry["units"], entry["format"]) == (len(STL), "mm", "stl-binary")


def test_completion_criterion_every_op_has_an_effect_block() -> None:
    r = build_manifest(**inputs())
    assert r.document is not None
    effects = [op["effect"] for op in r.document["operations"]]
    assert len(effects) == len(ops())
    assert effects == [
        {"positive_surface": "outward", "device_inner_surface": "more space"},
        {"positive_surface": "inward", "device_inner_surface": "less space"},
        {"positive_surface": "unchanged", "device_inner_surface": "unchanged"},
    ]
    missing = ops()
    del missing[1]["positive_surface"]
    bad = build_manifest(**inputs(operations=missing))
    assert bad.reason_code == MANIFEST_INCOMPLETE
    assert "/operations/1/effect/positive_surface" in bad.detail


# --- content -------------------------------------------------------------------------------------


def test_bytes_are_jcs_and_the_sha_is_of_the_bytes() -> None:
    r = build_manifest(**inputs())
    assert r.data is not None and r.document is not None
    assert r.sha256 == hashlib.sha256(r.data).hexdigest()
    assert parse_json(r.data.decode("utf-8")) == r.document
    keys = list(json.loads(r.data))
    assert keys == sorted(keys)  # canonical member order
    assert b" " not in r.data.replace(b"Test statement", b"").split(b"intended_use")[0][:50]


def test_fr103_fields_are_carried() -> None:
    d = build_manifest(**inputs()).document
    assert d is not None
    assert d["case_id"] == "J-0123ABCD" and d["design_version"] == {
        "id": inputs()["design_version_id"],
        "number": 2,
    }
    assert d["frame"] == {"name": "F_export", "matrix": EXPORT_FRAME,
                          "definition_ref": "export-rule/test", "config_version": 7}  # fmt: skip
    assert d["operations"][0]["category"] == "test-category-a"
    assert d["operations"][0]["name"] == "Зона 1"
    assert d["operations"][0]["params"] == {"magnitude_mm": 2.5}
    assert "positive_surface" not in d["operations"][0]  # only inside the effect block
    assert d["approval"]["approval_id"] == "ap-1" and d["template_ref"] is None
    assert d["software"] == {"build": "jude 0.1.0+test", "kernel_version": KERNEL_VERSION}
    assert d["reimport_check"]["tolerance_mm"] == 1e-4


def test_same_inputs_give_the_same_bytes_and_any_change_changes_the_sha() -> None:
    a, b = build_manifest(**inputs()), build_manifest(**inputs())
    assert a.data == b.data and a.sha256 == b.sha256
    other_stl = bytearray(STL)
    other_stl[100] ^= 1
    assert build_manifest(**inputs(stl=bytes(other_stl))).sha256 != a.sha256
    assert build_manifest(**inputs(config_version=8)).sha256 != a.sha256


def test_inputs_are_not_mutated() -> None:
    kw = inputs()
    before = copy.deepcopy(kw)
    build_manifest(**kw)
    assert kw == before


def test_device_side_convention_is_one_to_one() -> None:  # SAF-10
    assert DEVICE_SIDE == {"outward": "more space", "inward": "less space",
                           "unchanged": "unchanged"}  # fmt: skip
    schema_effect = MANIFEST_SCHEMA["properties"]["operations"]["items"]["properties"]["effect"]
    assert schema_effect["properties"]["positive_surface"]["enum"] == list(DEVICE_SIDE)
    assert schema_effect["properties"]["device_inner_surface"]["enum"] == list(DEVICE_SIDE.values())


def test_an_empty_op_list_and_no_index_values_are_valid() -> None:
    r = build_manifest(**inputs(operations=[], index_values=[]))
    assert r.reason_code is None


# --- MANIFEST_INCOMPLETE (one negative test per error code) -------------------------------------


@pytest.mark.parametrize(
    ("over", "pointer"),
    [
        ({"case_id": None}, "/case_id"),
        ({"case_id": ""}, "/case_id"),
        ({"frame_matrix": None}, "/frame/matrix"),
        ({"source_scan_sha256": None}, "/source_scan_sha256"),
        ({"software_build": None}, "/software/build"),
        ({"intended_use_statement": ""}, "/intended_use_statement"),
        ({"created_at_utc": None}, "/created_at_utc"),
        ({"approval": {}}, "/approval/approval_id"),
        ({"reimport_check": {"passed": True}}, "/reimport_check/tolerance_mm"),
    ],
)
def test_manifest_incomplete(over: dict[str, Any], pointer: str) -> None:
    r = build_manifest(**inputs(**over))
    assert (r.reason_code, r.document, r.data, r.sha256) == (MANIFEST_INCOMPLETE, None, None, None)
    assert pointer in r.detail.split(", ")


def test_index_value_without_definition_is_incomplete() -> None:  # SAF-06
    values = [{"name": "CI", "value": 81.25, "unit": "%"}]
    r = build_manifest(**inputs(index_values=values))
    assert r.reason_code == MANIFEST_INCOMPLETE
    assert r.detail.split(", ") == ["/index_values/0/definition_id",
                                    "/index_values/0/definition_version"]  # fmt: skip


def test_all_missing_fields_are_listed_in_order() -> None:
    r = build_manifest(**inputs(case_id=None, config_version=None))
    assert r.detail == "/case_id, /frame/config_version"


# --- contract (caller bugs) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "over",
    [
        {"stl": "not bytes"},
        {"stl": STL[:-1]},  # truncated
        {"stl": b"short"},
        {"frame_matrix": [2.0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]},  # scale
        {"frame_matrix": [-1.0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]},  # mirror
        {"design_version_number": "2"},  # wrong type
        {"source_scan_sha256": "ABC"},  # not a sha
        {"operations": [{**ops()[0], "positive_surface": "sideways"}]},  # outside the enum
        {"created_at_utc": "2026-11-28 09:05"},  # not UTC ISO-8601
        {"approval": {**inputs()["approval"], "extra": 1}},  # unknown member
    ],
)
def test_contract(over: dict[str, Any]) -> None:
    with pytest.raises(KernelContractError):
        build_manifest(**inputs(**over))


# --- properties ----------------------------------------------------------------------------------

op_strategy = st.fixed_dictionaries({
    "type": st.sampled_from(["zone.relief", "offset.normal", "adjust.global"]),
    "op_version": st.integers(1, 9),
    "category": st.one_of(st.none(), st.text(min_size=1, max_size=12)),
    "name": st.one_of(st.none(), st.text(min_size=1, max_size=12)),
    "params": st.dictionaries(st.text(min_size=1, max_size=8),
                              st.floats(-50, 50, allow_nan=False), max_size=3),
    "positive_surface": st.sampled_from(sorted(DEVICE_SIDE)),
})  # fmt: skip


@settings(max_examples=150, deadline=None)
@given(st.lists(op_strategy, max_size=8))
def test_property_valid_canonical_and_one_effect_per_op(op_list: list[dict[str, Any]]) -> None:
    numbered = [{"seq": i + 1, **op} for i, op in enumerate(op_list)]
    r = build_manifest(**inputs(operations=numbered))
    assert r.reason_code is None and r.data is not None and r.document is not None
    jsonschema.validate(json.loads(r.data), MANIFEST_SCHEMA, cls=jsonschema.Draft202012Validator)
    out = r.document["operations"]
    assert [o["seq"] for o in out] == list(range(1, len(op_list) + 1))  # order kept
    for src, o in zip(op_list, out, strict=True):
        assert o["effect"]["device_inner_surface"] == DEVICE_SIDE[src["positive_surface"]]
    assert build_manifest(**inputs(operations=copy.deepcopy(numbered))).data == r.data
