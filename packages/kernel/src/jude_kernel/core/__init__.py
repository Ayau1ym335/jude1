"""Kernel contracts (XC-FND-12): DS-01 MeshArrays, jude-arr/1, DS-03 OpSpec, DS-05 OpResult,
IF-03 runner."""

from jude_kernel.core.errors import JarrFormatError, KernelContractError
from jude_kernel.core.jarr import decode, decode_mesh, encode, encode_mesh
from jude_kernel.core.mesh import FaceTag, Frame, MeshArrays, check_caps
from jude_kernel.core.registry import REGISTRY, OpSpec, Registry
from jude_kernel.core.result import OpOutcome, OpResult, OpStatus
from jude_kernel.core.runner import ParamValidator, run

__all__ = [
    "REGISTRY",
    "FaceTag",
    "Frame",
    "JarrFormatError",
    "KernelContractError",
    "MeshArrays",
    "OpOutcome",
    "OpResult",
    "OpSpec",
    "OpStatus",
    "ParamValidator",
    "Registry",
    "check_caps",
    "decode",
    "decode_mesh",
    "encode",
    "encode_mesh",
    "run",
]
