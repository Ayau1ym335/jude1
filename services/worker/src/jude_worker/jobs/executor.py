"""Running a job handler (FN-JOB-02 step 3; SEC-07, SAF-09).

``ForkExecutor`` (production, Linux): the handler runs in a forked child with CPU-time and
memory limits (setrlimit), so a runaway job cannot take the worker down. While the child runs,
the parent calls ``tick`` every lease/3 to extend the lease; if the lease is lost, the child is
killed and the outcome dropped. A child killed by its CPU limit or out of memory gives
``resource_limit`` -> JOB_RESOURCE_LIMIT (no retry; the last valid geometry is untouched
because nothing is written, SAF-09).

``InlineExecutor``: same contract in-process, without limits (tests, non-Linux development).

Limits are deployment settings with no default in code: JUDE_JOB_CPU_SECONDS and
JUDE_JOB_MEMORY_MB (memory on top of the worker's own footprint at fork time).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import os
import signal
import sys
import traceback
from typing import Any, Literal

from jude_kernel.core import OpResult, OpStatus
from jude_worker.jobs.context import result_envelope

Handler = Callable[[Mapping[str, Any]], OpResult]
Tick = Callable[[], bool]
Kind = Literal["ok", "rejected", "failed", "error", "resource_limit", "lease_lost"]


@dataclass(frozen=True)
class Outcome:
    kind: Kind
    envelope: dict[str, Any] | None = None
    code: str | None = None


def outcome_of(result: OpResult, correlation_id: str) -> Outcome:
    env = result_envelope(result, correlation_id)
    if result.status is OpStatus.OK:
        return Outcome("ok", env)
    kind: Kind = "rejected" if result.status is OpStatus.REJECTED else "failed"
    return Outcome(kind, env, result.reason_code)


@dataclass(frozen=True)
class Limits:
    cpu_seconds: int
    memory_mb: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Limits":
        try:
            cpu, mem = int(env["JUDE_JOB_CPU_SECONDS"]), int(env["JUDE_JOB_MEMORY_MB"])
        except (KeyError, ValueError) as exc:
            raise RuntimeError(
                "JUDE_JOB_CPU_SECONDS and JUDE_JOB_MEMORY_MB must be set (no default, SEC-07)"
            ) from exc
        if cpu < 1 or mem < 1:
            raise RuntimeError("job limits must be positive")
        return cls(cpu, mem)


class InlineExecutor:
    def run(
        self, handler: Handler, payload: Mapping[str, Any], correlation_id: str, tick: Tick
    ) -> Outcome:
        try:
            result = handler(payload)
        except MemoryError:
            return Outcome("resource_limit", code="JOB_RESOURCE_LIMIT")
        except Exception as exc:  # infrastructure error: retry decision is the loop's
            return Outcome("error", code=type(exc).__name__)
        if not tick():
            return Outcome("lease_lost")
        return outcome_of(result, correlation_id)


def _vm_size_bytes() -> int:
    with open("/proc/self/status", encoding="ascii") as fh:
        for line in fh:
            if line.startswith("VmSize:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("VmSize not found")


class ForkExecutor:  # pragma: no cover - exercised on Linux (CI unit stage, worker image)
    def __init__(self, limits: Limits, lease_s: float) -> None:
        if not sys.platform.startswith("linux"):
            raise RuntimeError("ForkExecutor needs Linux (fork + setrlimit)")
        self.limits = limits
        self.tick_s = lease_s / 3.0

    def run(
        self, handler: Handler, payload: Mapping[str, Any], correlation_id: str, tick: Tick
    ) -> Outcome:
        import multiprocessing as mp
        import resource

        ctx = mp.get_context("fork")
        recv, send = ctx.Pipe(duplex=False)
        limits = self.limits

        def child() -> None:
            resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds + 1))
            cap = _vm_size_bytes() + limits.memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
            try:
                send.send(outcome_of(handler(payload), correlation_id))
            except MemoryError:
                send.send(Outcome("resource_limit", code="JOB_RESOURCE_LIMIT"))
            except Exception as exc:
                traceback.clear_frames(exc.__traceback__)
                send.send(Outcome("error", code=type(exc).__name__))

        proc = ctx.Process(target=child, daemon=True)
        proc.start()
        send.close()
        try:
            while True:
                if recv.poll(self.tick_s):
                    got: Outcome = recv.recv()
                    proc.join(5)
                    return got
                if not proc.is_alive():
                    break
                if not tick():
                    proc.kill()
                    return Outcome("lease_lost")
        except EOFError:
            pass
        proc.join(5)
        if proc.exitcode in (-signal.SIGXCPU, -signal.SIGKILL, -signal.SIGSEGV):
            return Outcome("resource_limit", code="JOB_RESOURCE_LIMIT")
        return Outcome("error", code=f"exit {proc.exitcode}")
