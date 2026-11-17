"""Jude geometry kernel (K01-K09).

Pure package: no I/O, clock, randomness, global mutable state or network
(DEVELOPMENT_STANDARDS §5, contract IF-03). Contents arrive with XC-FND-12
(MeshArrays, jude-arr/1, OpResult, runner); this module is only the anchor.
"""

__all__ = ["KERNEL_VERSION"]

KERNEL_VERSION = "0.0.0"
