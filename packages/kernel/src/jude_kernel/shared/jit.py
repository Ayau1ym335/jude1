"""The one sanctioned way to compile kernel code with numba (TD-02, TD-19, X-06 §6.2).

Every numba function in the kernel uses ``kernel_jit``; ruff bans ``numba.njit`` and its
relatives everywhere else in the kernel. The options are fixed here:

- ``fastmath=False``: no FMA contraction, no reassociation (bit-exact results, X-06).
- ``parallel=False``: single-threaded numerics (TD-19).
- ``error_model="numpy"``: division by zero follows IEEE (inf/nan) instead of raising, the same
  in compiled and interpreted code.
- ``cache=True``: compiled code is cached on disk (NUMBA_CACHE_DIR), so the worker image can
  ship a filled cache and start warm (X-06 §6.3). The CPU target comes from the environment;
  images set NUMBA_CPU_NAME=generic so the cache is valid on any amd64 host.
"""

from collections.abc import Callable
from typing import Any, Final, cast

import numba

KERNEL_JIT_OPTIONS: Final[dict[str, object]] = {
    "fastmath": False,
    "parallel": False,
    "error_model": "numpy",
    "cache": True,
    "nogil": False,
    "boundscheck": False,
}


def kernel_jit[F: Callable[..., Any]](fn: F) -> F:
    """Compile ``fn`` in nopython mode with the kernel's fixed options."""
    njit: Any = numba.njit
    return cast(F, njit(**KERNEL_JIT_OPTIONS)(fn))
