"""Compile or load every numba kernel once (X-06 §6.4: the worker warms up before it is ready).

Each numba module contributes its own ``warm_up``; add new modules (BVH, XC-SHR-02) here.
"""

from jude_kernel.shared import predicates

MODULES = (predicates,)


def warm_up() -> list[str]:
    """Run every module's warm-up; return the module names, in order."""
    names = []
    for module in MODULES:
        module.warm_up()
        names.append(module.__name__)
    return names
