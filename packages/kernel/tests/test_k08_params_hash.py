"""UT-FN-KRP-03 / PT-FN-KRP-03: canonical parameter-list hash (ALG-55, RFC 8785; TSK-KRP-03-K).

Completion criterion: key order or whitespace changes do not change the hash; any value change
does. ALG-55 verification: RFC 8785 test vectors (number formatting from Appendix B, key
sorting and the example object from section 3.2). The number vectors were also checked once
against an ECMAScript engine (Node ``JSON.stringify``) over 200 000 random doubles, with no
mismatch.
"""

import json
import math
import random
import struct
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest

from jude_kernel.core import KernelContractError
from jude_kernel.k08_replay import (
    PARAMS_SCHEMA,
    es_number,
    jcs_bytes,
    parameter_document,
    params_sha256,
    parse_json,
)

# RFC 8785 Appendix B: IEEE-754 bit pattern -> ECMAScript / JCS text.
APPENDIX_B = [
    ("0000000000000000", "0"),
    ("8000000000000000", "0"),
    ("0000000000000001", "5e-324"),
    ("8000000000000001", "-5e-324"),
    ("7fefffffffffffff", "1.7976931348623157e+308"),
    ("ffefffffffffffff", "-1.7976931348623157e+308"),
    ("4340000000000000", "9007199254740992"),
    ("c340000000000000", "-9007199254740992"),
    ("4430000000000000", "295147905179352830000"),
    ("44b52d02c7e14af5", "9.999999999999997e+22"),
    ("44b52d02c7e14af6", "1e+23"),
    ("44b52d02c7e14af7", "1.0000000000000001e+23"),
    ("444b1ae4d6e2ef4e", "999999999999999700000"),
    ("444b1ae4d6e2ef4f", "999999999999999900000"),
    ("444b1ae4d6e2ef50", "1e+21"),
    ("3eb0c6f7a0b5ed8c", "9.999999999999997e-7"),
    ("3eb0c6f7a0b5ed8d", "0.000001"),
    ("41b3de4355555553", "333333333.3333332"),
    ("41b3de4355555554", "333333333.33333325"),
    ("41b3de4355555555", "333333333.3333333"),
    ("41b3de4355555556", "333333333.3333334"),
    ("41b3de4355555557", "333333333.33333343"),
    ("becbf647612f3696", "-0.0000033333333333333333"),
    ("43143ff3c1cb0959", "1424953923781206.2"),
]

LS = chr(0x2028)  # LINE SEPARATOR: literal in JCS (ES2019 JSON.stringify)
IDENTITY = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def doc(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "cleanup_ops": [{"type": "cleanup.remove_faces", "op_version": 1, "faces": [3, 7, 9]}],
        "frame_id": "8a3c2f9e-1b7d-4e5f-9a0b-c1d2e3f4a5b6",
        "frame_matrix": IDENTITY,
        "design_ops": [
            {
                "type": "offset.uniform_normal",
                "op_version": 1,
                "params": {"magnitude_mm": 2.5},
                "enabled": True,
            },
            {
                "type": "zone.normal_falloff",
                "op_version": 2,
                "params": {"name": "Зона лобная", "magnitude_mm": -1.25, "radius_mm": 30.0},
                "enabled": False,
            },
        ],
        "template_ref": None,
        "config_version": 3,
    }
    base.update(changes)
    return parameter_document(**base)


# --- completion criterion ---------------------------------------------------------------------


def test_completion_criterion_key_order_and_whitespace_do_not_change_the_hash() -> None:
    d = doc()
    text = json.dumps(d)
    variants = [
        json.dumps(d, indent=4),
        json.dumps(d, separators=(",", ":")),
        json.dumps(dict(reversed(list(d.items()))), indent="\t"),
        json.dumps(d, ensure_ascii=True),  # \u escapes instead of literal Cyrillic
        " \n\t" + text.replace(":", " :\n ") + "\r\n",
    ]
    h = params_sha256(d)
    for v in variants:
        assert params_sha256(parse_json(v)) == h


def test_completion_criterion_any_value_change_changes_the_hash() -> None:
    base = params_sha256(doc())
    ops = doc()["design_ops"]

    def with_op(i: int, **patch: Any) -> dict[str, Any]:
        changed = [dict(o) for o in ops]
        changed[i] = {**changed[i], **patch}
        return doc(design_ops=changed)

    m = list(IDENTITY)
    m[3] = math.nextafter(0.0, 1.0)
    changed = [
        with_op(0, params={"magnitude_mm": math.nextafter(2.5, 3.0)}),  # one ulp
        with_op(0, params={"magnitude_mm": 2.5, "extra": None}),
        with_op(1, params={**ops[1]["params"], "name": "Зона лобна"}),  # one character
        with_op(1, enabled=True),
        with_op(1, op_version=3),
        doc(design_ops=list(reversed(ops))),  # op order is part of the design
        doc(config_version=4),
        doc(template_ref="tpl-1"),
        doc(frame_id="8a3c2f9e-1b7d-4e5f-9a0b-c1d2e3f4a5b7"),
        doc(frame_matrix=m),
        doc(cleanup_ops=[]),
        doc(cleanup_ops=[{"type": "cleanup.remove_faces", "op_version": 1, "faces": [3, 9, 7]}]),
    ]
    hashes = {params_sha256(d) for d in changed}
    assert base not in hashes and len(hashes) == len(changed)


# --- RFC 8785 vectors ---------------------------------------------------------------------------


@pytest.mark.parametrize(("bits", "text"), APPENDIX_B)
def test_rfc8785_appendix_b_numbers(bits: str, text: str) -> None:
    value = struct.unpack(">d", bytes.fromhex(bits))[0]
    assert es_number(value) == text
    assert jcs_bytes(value) == text.encode()


def test_rfc8785_key_sorting_uses_utf16_code_units() -> None:
    # RFC 8785 section 3.2.3: U+1F600 (surrogates D83D DE00) sorts *before* U+FB33.
    keys = ["€", "\r", "דּ", "1", "\U0001f600", "\u0080", "ö"]
    obj = {k: i for i, k in enumerate(keys)}
    expected_order = ["\r", "1", "\u0080", "ö", "€", "\U0001f600", "דּ"]
    inner = ",".join(json.dumps(k, ensure_ascii=False) + ":" + str(keys.index(k))
                     for k in expected_order)  # fmt: skip
    assert jcs_bytes(obj) == ("{" + inner.replace('"\\r"', '"\\r"') + "}").encode()
    assert sorted(keys) != expected_order  # code-point order would differ


def test_rfc8785_example_object() -> None:
    # RFC 8785 section 3.2: input with mixed number forms and escapes, and its canonical form.
    source = (
        '{"numbers":[333333333.33333329,1E30,4.50,2e-3,0.000000000000000000000000001],'
        '"string":"\\u20ac$\\u000F\\u000aA\'\\u0042\\u0022\\u005c\\\\\\"\\/",'
        '"literals":[null,true,false]}'
    )
    expected = (
        '{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
        '"string":"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'
    )
    assert jcs_bytes(parse_json(source)) == expected.encode("utf-8")


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ({"b": 1, "a": [1.0, -0.0, 10.0, 0.1]}, '{"a":[1,0,10,0.1],"b":1}'),
        (
            {"s": "tab	here " + chr(0x7F) + " " + chr(1) + " " + LS},
            '{"s":"tab\\there ' + chr(0x7F) + " \\u0001 " + LS + '"}',
        ),
        ({"Имя": "значение"}, '{"Имя":"значение"}'),
        ([], "[]"),
        ({}, "{}"),
        ((1, (2,)), "[1,[2]]"),
    ],
)
def test_serialisation_details(value: Any, text: str) -> None:
    assert jcs_bytes(value) == text.encode("utf-8")


@pytest.mark.determinism
def test_golden_params_hash_is_stable() -> None:
    golden = (
        "80ceda3e9b857abcc4be57e06fc217b33bd93210ccd74278a8cab1c166d0923c"  # = Node JSON.stringify
    )
    assert params_sha256(doc()) == golden


# --- property tests -----------------------------------------------------------------------------

json_leaf = (
    st.none() | st.booleans() | st.integers(min_value=-(2**53), max_value=2**53)
    | st.floats(allow_nan=False, allow_infinity=False) | st.text(max_size=12)
)  # fmt: skip
json_value = st.recursive(
    json_leaf,
    lambda inner: (
        st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=6), inner, max_size=4)
    ),
    max_leaves=20,
)


@settings(max_examples=300, deadline=None)
@given(value=st.dictionaries(st.text(max_size=6), json_value, max_size=6), seed=st.integers())
def test_property_member_order_and_whitespace_are_irrelevant(
    value: dict[str, Any], seed: int
) -> None:
    try:
        jcs_bytes(value)
    except KernelContractError:
        return  # lone surrogates from st.text are refused by design (tested below)
    items = list(value.items())
    random.Random(seed).shuffle(items)  # noqa: S311 - test reordering, not security
    reordered = json.dumps(dict(items), indent=seed % 5 or None, ensure_ascii=bool(seed % 2))
    assert params_sha256(parse_json(reordered)) == params_sha256(value)
    # parse(JCS(x)) is a fixed point
    assert jcs_bytes(parse_json(jcs_bytes(value).decode("utf-8"))) == jcs_bytes(value)


@settings(max_examples=300, deadline=None)
@given(x=st.floats(allow_nan=False, allow_infinity=False))
def test_property_numbers_round_trip_and_one_ulp_differs(x: float) -> None:
    text = es_number(x)
    assert float(text) == x  # shortest round-trip: the text names exactly this double
    up = math.nextafter(x, math.inf)
    if math.isfinite(up) and up != x and not (x == 0 and up == 0):
        assert params_sha256({"v": up}) != params_sha256({"v": x})


# --- contract -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [math.nan, math.inf, -math.inf, 2**53 + 1, -(2**53) - 1, {1: "x"}, b"bytes", {1.5},
     object(), "lone \ud800 surrogate", {"\udfff": 1}],
)  # fmt: skip
def test_non_json_values_are_refused(value: Any) -> None:
    with pytest.raises(KernelContractError):
        jcs_bytes(value)


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"a":NaN}', "[Infinity]", '{"a":', ""])
def test_strict_parsing(text: str) -> None:
    with pytest.raises(KernelContractError):
        parse_json(text)


def test_parameter_document_shape_and_validation() -> None:
    d = doc()
    assert d["schema"] == PARAMS_SCHEMA and list(d) == [
        "schema", "cleanup_ops", "frame", "design_ops", "template_ref", "config_version",
    ]  # fmt: skip
    op = d["design_ops"][0]
    for bad in (
        {"frame_matrix": IDENTITY[:15]},
        {"frame_matrix": [math.nan, *IDENTITY[1:]]},
        {"frame_id": ""},
        {"config_version": True},
        {"config_version": "3"},
        {"template_ref": 7},
        {"design_ops": [{**op, "extra": 1}]},
        {"design_ops": [{k: v for k, v in op.items() if k != "enabled"}]},
        {"design_ops": [{**op, "enabled": 1}]},
    ):
        with pytest.raises(KernelContractError):
            doc(**bad)


def test_inputs_are_not_modified() -> None:
    ops = [{"type": "x", "op_version": 1, "params": {"a": 1}, "enabled": True}]
    before = json.dumps(ops)
    d = doc(design_ops=ops)
    d["design_ops"][0]["type"] = "changed"
    assert json.dumps(ops) == before
