"""Jude geometry kernel (K01-K09).

Pure package: no I/O, clock, randomness, global mutable state or network
(DEVELOPMENT_STANDARDS §5, contract IF-03). Contracts live in ``jude_kernel.core``.
"""

from jude_kernel.version import KERNEL_VERSION

__all__ = ["KERNEL_VERSION"]
