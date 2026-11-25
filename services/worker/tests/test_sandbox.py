"""XC-FND-09: worker sandbox for untrusted parsing (SEC-07, IDR-07, TQ-20).

Completion criterion: face-bomb, zip-bomb-like and truncated fixtures terminate the child only;
the worker stays healthy. The real STL/OBJ/PLY parsers arrive with TSK-KIO-02..04 and run in
this sandbox. Here a deliberately naive parser, which trusts the counts in the file, stands in
for a parser bug: whatever it does, only the child dies.

The confinement tests need Linux x86-64 (fork, setrlimit, seccomp). They run in the CI unit
stage on Linux and are skipped elsewhere.
"""

from collections.abc import Mapping
import ctypes
import gzip
import os
from pathlib import Path
import platform
import socket
import struct
import subprocess
import sys
from typing import Any

import numpy as np
import pytest

from jude_kernel.core import Frame, MeshArrays, OpResult, OpStatus
from jude_worker.jobs.executor import ForkExecutor, Limits, Outcome
from jude_worker.jobs.sandbox import (
    AUDIT_ARCH_X86_64,
    DENIED_SYSCALLS,
    SECCOMP_RET_ALLOW,
    SECCOMP_RET_KILL_PROCESS,
    seccomp_program,
)

T3 = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "T3"
linux_x86 = pytest.mark.skipif(
    not (sys.platform.startswith("linux") and platform.machine() in ("x86_64", "AMD64")),
    reason="fork + setrlimit + x86-64 seccomp",
)
LIMITS = Limits(cpu_seconds=2, memory_mb=256)
PROBE = "/tmp/jude-sandbox-probe"  # noqa: S108 - the writable tmpfs of the worker container


def ok_result() -> OpResult:
    mesh = MeshArrays.create(np.eye(3), np.array([[0, 1, 2]]), frame=Frame.F_SCAN)
    return OpResult(status=OpStatus.OK, op_type="t.op", op_version=1, outputs={"m": mesh},
                    report={}, reason_code=None, kernel_version="0.0.0",
                    image_digest="sha256:" + "0" * 64, lib_versions={})  # fmt: skip


def run(handler: Any, payload: Mapping[str, Any] | None = None) -> Outcome:
    return ForkExecutor(LIMITS, lease_s=30.0).run(handler, payload or {}, "c" * 16, lambda: True)


# --- handlers a hostile file could make a parser do -----------------------------------------------


def naive_stl(payload: Mapping[str, Any]) -> OpResult:
    """A parser bug on purpose: trusts the triangle count of a binary STL header."""
    data = Path(payload["path"]).read_bytes()
    (n,) = struct.unpack_from("<I", data, 80)
    triangles = np.empty((n, 12), dtype="<f4")  # 2**31 claimed -> ~100 GiB
    triangles[: (len(data) - 84) // 50] = 0
    return ok_result()


def naive_inflate(payload: Mapping[str, Any]) -> OpResult:
    gzip.decompress(Path(payload["path"]).read_bytes())  # a decompression bomb, fully inflated
    return ok_result()


def strict_truncated(payload: Mapping[str, Any]) -> OpResult:
    data = Path(payload["path"]).read_bytes()
    (n,) = struct.unpack_from("<I", data, 80)
    for i in range(n):
        struct.unpack_from("<12fH", data, 84 + 50 * i)  # runs off the end -> struct.error
    return ok_result()


def open_socket(_: Mapping[str, Any]) -> OpResult:
    socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    return ok_result()


def exec_program(_: Mapping[str, Any]) -> OpResult:
    subprocess.run(["/bin/true"], check=False)
    return ok_result()


def write_file(_: Mapping[str, Any]) -> OpResult:
    with open(PROBE, "wb") as fh:
        fh.write(b"x" * 4096)
        fh.flush()
    return ok_result()


def segfault(_: Mapping[str, Any]) -> OpResult:
    ctypes.string_at(0)
    return ok_result()


def benign(_: Mapping[str, Any]) -> OpResult:
    return ok_result()


# --- completion criterion -----------------------------------------------------------------------


@linux_x86
def test_completion_criterion_bomb_and_truncated_fixtures_kill_only_the_child(
    tmp_path: Path,
) -> None:
    face_bomb = T3 / "face_bomb" / "face_bomb.stl"
    truncated = next((T3 / "truncated").glob("*.stl"))
    bomb = tmp_path / "bomb.gz"
    with gzip.open(bomb, "wb", compresslevel=9) as fh:  # ~1 MiB that inflates to 1 GiB
        chunk = bytes(16 * 1024 * 1024)
        for _ in range(64):
            fh.write(chunk)
    assert bomb.stat().st_size < 4 * 1024 * 1024

    assert run(naive_stl, {"path": str(face_bomb)}).code == "JOB_RESOURCE_LIMIT"
    assert run(naive_inflate, {"path": str(bomb)}).code == "JOB_RESOURCE_LIMIT"
    assert run(strict_truncated, {"path": str(truncated)}) == Outcome("error", code="error")
    # the worker (this process) is unaffected and keeps working
    assert run(benign).kind == "ok"
    probe = socket.socket()
    probe.close()


# --- confinement ----------------------------------------------------------------------------------


@linux_x86
@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (open_socket, Outcome("error", code="PermissionError")),  # no network
        (exec_program, Outcome("error", code="PermissionError")),  # no exec
        (write_file, Outcome("error", code="OSError")),  # no writes (RLIMIT_FSIZE 0: EFBIG)
        (segfault, Outcome("resource_limit", code="JOB_RESOURCE_LIMIT")),  # child crash only
    ],
    ids=["network", "exec", "write", "segfault"],
)
def test_the_child_cannot_reach_out(handler: Any, expected: Outcome) -> None:
    assert run(handler) == expected
    assert not os.path.exists(PROBE) or os.path.getsize(PROBE) == 0
    assert run(benign).kind == "ok"  # the worker carries on


# --- the BPF program (any platform) ---------------------------------------------------------------


def _insns(program: bytes) -> list[tuple[int, int, int, int]]:
    return [struct.unpack_from("=HBBI", program, i) for i in range(0, len(program), 8)]


def test_seccomp_program_shape() -> None:
    denied = sorted(DENIED_SYSCALLS.values())
    insns = _insns(seccomp_program(denied))
    assert len(insns) == 4 + 1 + len(denied) + 3
    assert insns[0] == (0x20, 0, 0, 4)  # load arch
    assert insns[1][3] == AUDIT_ARCH_X86_64 and insns[2][3] == SECCOMP_RET_KILL_PROCESS
    assert insns[3] == (0x20, 0, 0, 0)  # load syscall nr
    assert [i[3] for i in insns[5 : 5 + len(denied)]] == denied
    assert insns[-3][3] == SECCOMP_RET_ALLOW
    assert insns[-2][3] == 0x00050001  # ERRNO | EPERM
    assert insns[-1][3] == SECCOMP_RET_KILL_PROCESS


def test_every_check_jumps_to_the_right_return() -> None:
    denied = sorted(DENIED_SYSCALLS.values())
    insns = _insns(seccomp_program(denied))
    deny, kill = len(insns) - 2, len(insns) - 1
    x32 = 4
    assert x32 + 1 + insns[x32][1] == kill  # x32 ABI -> kill
    for pc in range(5, 5 + len(denied)):
        assert pc + 1 + insns[pc][1] == deny, pc  # each denied syscall -> EPERM
    assert 1 + 1 + insns[1][1] == 3  # right architecture -> continue to the nr load


def test_network_exec_and_namespace_syscalls_are_denied() -> None:
    network = {"socket", "connect", "bind", "listen", "accept", "accept4", "socketpair"}
    other = {"execve", "execveat", "ptrace", "unshare", "setns", "mount"}
    assert network | other <= set(DENIED_SYSCALLS)
