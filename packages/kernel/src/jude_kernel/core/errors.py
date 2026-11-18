"""Kernel contract errors.

These are programming or data-contract errors raised to the caller. Geometric refusals are
not exceptions: an op returns ``OpResult(status=rejected, reason_code=...)`` (SAF-09).
"""


class KernelContractError(ValueError):
    """A value does not satisfy a kernel data contract (DS-01, DS-03, DS-05, IF-03)."""


class JarrFormatError(ValueError):
    """Bytes are not a valid canonical jude-arr/1 container (IDR-15)."""
