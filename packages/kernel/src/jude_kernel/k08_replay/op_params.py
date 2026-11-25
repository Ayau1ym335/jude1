"""FN-KRP-04 Operation registry and parameter validation (ALG-61; TD-19; SAF-02, FR-055, FR-052).

Every op version has a JSON Schema 2020-12 document for its parameters (``OpSpec.params_schema``,
DS-03). Two things happen here:

**Request validation** (``check_request`` / ``validate_params``, the runner's ``ParamValidator``):

1. unknown (type, version) -> ``OP_UNKNOWN``;
2. a required key is missing -> ``PARAM_NOT_SET``. Nothing is ever defaulted (DEC-029): a value
   the clinic or technician has not given stays not set;
3. any other violation -> ``PARAM_INVALID``. This covers a wrong type, a structural bound (radius
   > 0, iterations >= 1, ...), an unknown key, NaN / Infinity, and an integer outside +-2^53
   (JSON numbers are doubles; ALG-61 step 3);
4. the result carries the JSON pointer of the offending value, and the validated params come
   back as a private copy, ready for the parameter hash (ALG-55, FN-KRP-03).

When several things are wrong, ``PARAM_NOT_SET`` wins (the step-2 refusal), then the
lexicographically first pointer. The same request therefore always gives the same answer.

**Schema rules** (``schema_problems`` / ``registry_problems``, the CI meta-test of INV-12):

- the schema is a valid JSON Schema 2020-12 document whose root is an object schema;
- **no ``default`` keyword anywhere**. ALG-61 forbids it on clinical/production keys; it is
  banned everywhere because the validator never fills values in, so a default could only
  mislead a reader into thinking a value is implied;
- every object schema has ``additionalProperties: false`` (unknown keys are rejected) and lists
  **every** declared property as required (everything explicit; ``null`` must be typed in);
- no remote ``$ref`` (validation never reaches outside the kernel).

``registry_fingerprint`` gives each (type, version) with the SHA-256 of its canonical schema. A
test compares it with a committed snapshot, so an op version cannot silently change its schema
(changing behaviour means a version bump) and old versions stay registered for replay.
"""

from collections.abc import Iterator, Mapping
import copy
from dataclasses import dataclass
import math
from typing import Any, Final

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from jude_kernel.core.registry import OpSpec, Registry
from jude_kernel.k08_replay.jcs import MAX_SAFE_INTEGER
from jude_kernel.k08_replay.params_hash import params_sha256

OP_UNKNOWN: Final = "OP_UNKNOWN"
PARAM_NOT_SET: Final = "PARAM_NOT_SET"
PARAM_INVALID: Final = "PARAM_INVALID"


@dataclass(frozen=True)
class ParamCheck:
    """Outcome of a request check: ``reason`` is None when the params are valid."""

    reason: str | None
    pointer: str = ""
    detail: str = ""
    params: Mapping[str, Any] | None = None


def _plain(node: Any) -> Any:
    """Plain dicts and lists: OpSpec freezes schemas as mappingproxy, which jsonschema rejects."""
    if isinstance(node, Mapping):
        return {k: _plain(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [_plain(v) for v in node]
    return node


def _pointer(path: Iterator[Any] | Any) -> str:
    parts = [str(p).replace("~", "~0").replace("/", "~1") for p in path]
    return "/" + "/".join(parts) if parts else ""


def _numbers(value: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[str, str]]:
    """(pointer, detail) of every non-finite float or unsafe integer inside ``value``."""
    if isinstance(value, bool):
        return
    if isinstance(value, float) and not math.isfinite(value):
        yield _pointer(path), "number must be finite"
    elif isinstance(value, int) and abs(value) > MAX_SAFE_INTEGER:
        yield _pointer(path), "integer outside +-2^53 is not exact as a JSON number"
    elif isinstance(value, Mapping):
        for k in value:
            yield from _numbers(value[k], (*path, k))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            yield from _numbers(item, (*path, i))


def validate_against(spec: OpSpec, params: Any) -> ParamCheck:
    """Check ``params`` against ``spec.params_schema`` (FN-KRP-04 steps 2-4)."""
    validator = Draft202012Validator(_plain(spec.params_schema))
    missing: list[tuple[str, str]] = []
    invalid: list[tuple[str, str]] = []
    for error in validator.iter_errors(params):
        where = list(error.absolute_path)
        if error.validator == "required" and isinstance(error.instance, Mapping):
            for key in error.validator_value:
                if key not in error.instance:
                    missing.append((_pointer([*where, key]), f"{key} is not set"))
        else:
            invalid.append((_pointer(where), f"{error.validator}: {error.message}"))
    invalid.extend(_numbers(params))
    if missing:
        pointer, detail = min(missing)
        return ParamCheck(PARAM_NOT_SET, pointer, detail)
    if invalid:
        pointer, detail = min(invalid)
        return ParamCheck(PARAM_INVALID, pointer, detail)
    return ParamCheck(None, params=copy.deepcopy(dict(params)))


def check_request(registry: Registry, op_type: str, op_version: int, params: Any) -> ParamCheck:
    """FN-KRP-04 for an op request: OP_UNKNOWN, PARAM_NOT_SET, PARAM_INVALID or valid params."""
    spec = registry.get(op_type, op_version)
    if spec is None:
        return ParamCheck(OP_UNKNOWN, "", f"{op_type} v{op_version} is not registered")
    return validate_against(spec, params)


def validate_params(spec: OpSpec, params: Mapping[str, Any]) -> str | None:
    """``ParamValidator`` for ``jude_kernel.core.run``: the reason code, or None when valid."""
    return validate_against(spec, params).reason


# --- schema rules (INV-12 meta-test) -------------------------------------------------------------


def _walk(node: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    yield path, node
    if isinstance(node, Mapping):
        for k in sorted(node):
            yield from _walk(node[k], (*path, str(k)))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk(item, (*path, str(i)))


def _is_object_schema(node: Mapping[str, Any]) -> bool:
    t = node.get("type")
    return t == "object" or (isinstance(t, list) and "object" in t) or "properties" in node


def schema_problems(schema: Mapping[str, Any]) -> list[str]:
    """Every violation of the schema rules, as readable strings (empty when the schema is fine)."""
    schema = _plain(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [f"not a valid JSON Schema 2020-12 document: {exc.message}"]
    problems = []
    if schema.get("type") != "object":
        problems.append("root: params must be an object schema")
    for path, node in _walk(schema):
        if not isinstance(node, Mapping):
            continue
        # A schema node, not the "properties" map whose keys are parameter names.
        if path and path[-1] == "properties":
            continue
        where = "/" + "/".join(path)
        if "default" in node:
            problems.append(f"{where}: 'default' is forbidden (DEC-029, INV-12)")
        ref = node.get("$ref")
        if isinstance(ref, str) and not ref.startswith("#"):
            problems.append(f"{where}: only local $ref is allowed")
        if _is_object_schema(node):
            if node.get("additionalProperties") is not False:
                problems.append(f"{where}: additionalProperties must be false")
            declared = set(node.get("properties", {}))
            required = set(node.get("required", []))
            if declared - required:
                missing = ", ".join(sorted(declared - required))
                problems.append(f"{where}: every property must be required (not: {missing})")
    return problems


def registry_problems(registry: Registry) -> dict[str, list[str]]:
    """Schema problems per registered op version (empty dict when every schema is fine)."""
    found = {}
    for spec in registry:
        problems = schema_problems(spec.params_schema)
        if problems:
            found[f"{spec.type} v{spec.version}"] = problems
    return found


def registry_fingerprint(registry: Registry) -> list[dict[str, Any]]:
    """[{type, version, schema_sha256}] sorted: the snapshot the registry test compares."""
    return [
        {"type": s.type, "version": s.version, "schema_sha256": params_sha256(s.params_schema)}
        for s in sorted(registry, key=lambda s: s.key)
    ]
