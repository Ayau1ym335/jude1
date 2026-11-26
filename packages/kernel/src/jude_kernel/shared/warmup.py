"""Compile or load every numba kernel once (X-06 §6.4: the worker warms up before it is ready).

Each numba module contributes its own ``warm_up``; every new numba module is added here.
"""

from jude_kernel.shared import bvh, predicates

MODULES = (predicates, bvh)


def warm_up() -> list[str]:
    """Run every module's warm-up; return the module names, in order."""
    names = []
    for module in MODULES:
        module.warm_up()
        names.append(module.__name__)
    return names
