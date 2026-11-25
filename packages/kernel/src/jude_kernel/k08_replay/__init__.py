"""K08 replay layer: canonical hashes and deterministic replay of the operation log."""

from jude_kernel.k08_replay.geometry_hash import (
    GEOMETRY_MAGIC,
    canonical_geometry_bytes,
    geometry_sha256,
    mesh_geometry_sha256,
)
from jude_kernel.k08_replay.jcs import es_number, jcs_bytes, parse_json
from jude_kernel.k08_replay.op_params import (
    OP_UNKNOWN,
    PARAM_INVALID,
    PARAM_NOT_SET,
    ParamCheck,
    check_request,
    registry_fingerprint,
    registry_problems,
    schema_problems,
    validate_against,
    validate_params,
)
from jude_kernel.k08_replay.params_hash import PARAMS_SCHEMA, parameter_document, params_sha256

__all__ = [
    "GEOMETRY_MAGIC",
    "OP_UNKNOWN",
    "PARAMS_SCHEMA",
    "PARAM_INVALID",
    "PARAM_NOT_SET",
    "ParamCheck",
    "canonical_geometry_bytes",
    "check_request",
    "es_number",
    "geometry_sha256",
    "jcs_bytes",
    "mesh_geometry_sha256",
    "parameter_document",
    "params_sha256",
    "parse_json",
    "registry_fingerprint",
    "registry_problems",
    "schema_problems",
    "validate_against",
    "validate_params",
]
