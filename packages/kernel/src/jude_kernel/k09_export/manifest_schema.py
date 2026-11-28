"""JSON Schema of the export manifest jude-manifest/0.1 (IDR-27, INT-05, DS-15).

This is the published schema. ``packages/kernel/schemas/jude-manifest-0.1.schema.json`` is a
generated copy of it for production and for FN-KEX-02 (a test keeps the two identical).

Fields (FR-103, DS-15, FN-KEX-01 inputs):

- ``schema``: the fixed id ``jude-manifest/0.1``.
- ``case_id``.
- ``design_version``: the version id and number.
- ``files``: the exported binary STL with its SHA-256 and units (mm, ALG-06).
- ``frame``: F_export as a row-major 4x4 matrix, with its definition reference and config
  version (DEC-015).
- ``source_scan_sha256``.
- ``operations``: the enabled design operations in order. Each one carries its category, its
  name, its params and an effect block (SAF-10).
- ``template_ref``.
- ``approval``: the approval record id and its hash binding.
- ``reimport_check``: the FR-102 re-import result.
- ``index_values``: every one carries a definition id and version (SAF-06); the list may be
  empty.
- ``software``: build and kernel version (NFR-08).
- ``created_at_utc``.
- ``intended_use_statement``: the SAF-01 text.

Every member is required and no value is defaulted (DEC-029). ``additionalProperties`` is false
everywhere: a field the schema does not name is a schema change, which means a new version.
"""

from typing import Any, Final

MANIFEST_SCHEMA_ID: Final = "jude-manifest/0.1"
SHA256: Final[dict[str, Any]] = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
TEXT: Final[dict[str, Any]] = {"type": "string", "minLength": 1}
UTC: Final[dict[str, Any]] = {
    "type": "string",
    "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$",
}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(properties),
        "properties": properties,
    }


EFFECT: Final = _object(
    {
        # SAF-10: one convention. The device is formed over the positive, so its inner surface
        # follows the positive surface: outward means more space, inward means less space.
        "positive_surface": {"enum": ["outward", "inward", "unchanged"]},
        "device_inner_surface": {"enum": ["more space", "less space", "unchanged"]},
    }
)

MANIFEST_SCHEMA: Final[dict[str, Any]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://jude.invalid/schemas/jude-manifest-0.1.schema.json",
    "title": "Jude export manifest",
    **_object(
        {
            "schema": {"const": MANIFEST_SCHEMA_ID},
            "case_id": TEXT,
            "design_version": _object({"id": TEXT, "number": {"type": "integer", "minimum": 1}}),
            "files": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "items": _object(
                    {
                        "name": TEXT,
                        "sha256": SHA256,
                        "format": {"const": "stl-binary"},
                        "units": {"const": "mm"},
                        "size_bytes": {"type": "integer", "minimum": 84},
                    }
                ),
            },
            "frame": _object(
                {
                    "name": {"const": "F_export"},
                    "matrix": {
                        "type": "array",
                        "minItems": 16,
                        "maxItems": 16,
                        "items": {"type": "number"},
                    },
                    "definition_ref": TEXT,
                    "config_version": {"type": "integer", "minimum": 1},
                }
            ),
            "source_scan_sha256": SHA256,
            "operations": {
                "type": "array",
                "items": _object(
                    {
                        "seq": {"type": "integer", "minimum": 1},
                        "type": TEXT,
                        "op_version": {"type": "integer", "minimum": 1},
                        "category": {"type": ["string", "null"]},
                        "name": {"type": ["string", "null"]},
                        "params": {"type": "object"},
                        "effect": EFFECT,
                    }
                ),
            },
            "template_ref": {"type": ["string", "null"]},
            "approval": _object(
                {
                    "approval_id": TEXT,
                    "geometry_sha256": SHA256,
                    "params_sha256": SHA256,
                    "approved_at_utc": UTC,
                }
            ),
            "reimport_check": _object(
                {
                    "passed": {"type": "boolean"},
                    "triangle_count_equal": {"type": "boolean"},
                    "max_vertex_deviation_mm": {"type": "number", "minimum": 0},
                    "tolerance_mm": {"type": "number", "exclusiveMinimum": 0},
                }
            ),
            "index_values": {
                "type": "array",
                "items": _object(
                    {
                        "name": TEXT,
                        "value": {"type": "number"},
                        "unit": TEXT,
                        "definition_id": TEXT,
                        "definition_version": {"type": "integer", "minimum": 1},
                    }
                ),
            },
            "software": _object({"build": TEXT, "kernel_version": TEXT}),
            "created_at_utc": UTC,
            "intended_use_statement": TEXT,
        }
    ),
}
