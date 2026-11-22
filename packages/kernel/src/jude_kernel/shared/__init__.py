"""Shared kernel building blocks: exact predicates (XC-SHR-01), later the BVH (XC-SHR-02).

Importing this package loads numba; ``jude_kernel`` itself does not import it, so the API and
tools that only need the kernel's data types never pay numba's import or JIT cost.
"""
