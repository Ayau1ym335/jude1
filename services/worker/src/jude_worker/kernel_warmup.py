"""Kernel warm-up at worker start (X-06 §6.3, §6.4).

The image compiles every numba kernel at build time into JUDE_NUMBA_PREFILLED_CACHE
(read-only at runtime). numba refuses a cache directory it cannot write, so at start the
prefilled cache is copied to NUMBA_CACHE_DIR on the /tmp tmpfs; then every kernel is loaded
before the health endpoint reports ready, so no user job pays the JIT cost.
"""

from collections.abc import Mapping
import logging
import os
from pathlib import Path
import shutil
import time

log = logging.getLogger("jude_worker.warmup")


def seed_cache(env: Mapping[str, str] = os.environ) -> bool:
    """Copy the prefilled cache into NUMBA_CACHE_DIR if both are set. Returns True if copied."""
    source, target = env.get("JUDE_NUMBA_PREFILLED_CACHE"), env.get("NUMBA_CACHE_DIR")
    if not source or not target or not Path(source).is_dir() or Path(target).exists():
        return False
    shutil.copytree(source, target)
    return True


def warm_up() -> float:
    """Seed the cache, load every kernel; returns the duration in seconds."""
    start = time.perf_counter()
    seeded = seed_cache()
    from jude_kernel.shared.warmup import (
        warm_up as kernel_warm_up,  # after seeding: numba reads the cache at import
    )

    modules = kernel_warm_up()
    seconds = time.perf_counter() - start
    log.info(
        "kernel.warmup",
        extra={
            "duration_ms": seconds * 1000.0,
            "ok": seeded,  # True: started from the image's prefilled cache
            "component": ",".join(m.rsplit(".", 1)[-1] for m in modules),
        },
    )
    return seconds
