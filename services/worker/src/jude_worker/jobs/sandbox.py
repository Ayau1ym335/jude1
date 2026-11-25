"""Worker sandbox for untrusted parsing (XC-FND-09; SEC-07, IDR-07, TQ-20).

Every job handler runs in a forked child (``ForkExecutor``). Before the handler starts,
``confine`` locks the child down, so a malformed or malicious file can at most kill that child:
- the worker stays healthy;
- the API never sees anything but a job outcome.

In the child, in this order:

1. **rlimits.**
   - CPU seconds and address space: the deployment's ``JUDE_JOB_CPU_SECONDS`` /
     ``JUDE_JOB_MEMORY_MB``, with no default (SEC-07);
   - no core dumps;
   - file size 0: nothing can be written, not even to the writable ``/tmp``, and SIGXFSZ is
     ignored so a write fails with EFBIG instead of killing the child;
   - a small cap on open files.
2. **no new privileges** (``PR_SET_NO_NEW_PRIVS``): no setuid binary can raise the child's
   rights, and an unprivileged seccomp filter becomes possible.
3. **seccomp-BPF filter** (x86-64, the image architecture of IDR-09). The network, exec,
   ptrace and namespace/mount syscalls fail with EPERM: no socket, connect, bind, listen,
   accept, execve, ptrace, mount, unshare or setns. Any foreign architecture, or the x32 ABI,
   kills the child.

The container adds the rest of IDR-07 (``compose.yaml``):
- read-only root filesystem and ``tmpfs /tmp``;
- non-root user 10001;
- ``no-new-privileges``;
- all capabilities dropped;
- a pid limit;
- Docker's default seccomp profile, which allows ``prctl`` / ``seccomp`` for this filter.

The filter is the strictest TQ-20 option that needs no extra runtime (gVisor). It is written
with ctypes against the stable kernel ABI (linux/filter.h, linux/seccomp.h); there is no
third-party dependency.
"""

from collections.abc import Sequence
import ctypes
import signal
import struct
from typing import Final

# linux/filter.h, linux/seccomp.h, linux/audit.h, linux/prctl.h (stable kernel ABI)
BPF_LD_W_ABS: Final = 0x20
BPF_JMP_JEQ_K: Final = 0x15
BPF_JMP_JGE_K: Final = 0x35
BPF_RET_K: Final = 0x06
SECCOMP_RET_KILL_PROCESS: Final = 0x80000000
SECCOMP_RET_ERRNO: Final = 0x00050000
SECCOMP_RET_ALLOW: Final = 0x7FFF0000
EPERM: Final = 1
AUDIT_ARCH_X86_64: Final = 0xC000003E
X32_SYSCALL_BIT: Final = 0x40000000
PR_SET_NO_NEW_PRIVS: Final = 38
PR_SET_SECCOMP: Final = 22
SECCOMP_MODE_FILTER: Final = 2
OFFSET_NR: Final = 0  # struct seccomp_data.nr
OFFSET_ARCH: Final = 4  # struct seccomp_data.arch

# x86-64 syscall numbers (arch/x86/entry/syscalls/syscall_64.tbl) refused in the child.
DENIED_SYSCALLS: Final = {
    "socket": 41, "connect": 42, "accept": 43, "bind": 49, "listen": 50, "socketpair": 53,
    "execve": 59, "ptrace": 101, "mount": 165, "umount2": 166, "unshare": 272,
    "accept4": 288, "setns": 308, "execveat": 322,
}  # fmt: skip
OPEN_FILES: Final = 64


def _insn(code: int, jt: int, jf: int, k: int) -> bytes:
    return struct.pack("=HBBI", code, jt, jf, k)


def seccomp_program(denied: Sequence[int]) -> bytes:
    """The BPF program: check the architecture, refuse the denied syscalls, allow the rest."""
    deny_ret = SECCOMP_RET_ERRNO | EPERM
    body = [
        _insn(BPF_LD_W_ABS, 0, 0, OFFSET_ARCH),
        _insn(BPF_JMP_JEQ_K, 1, 0, AUDIT_ARCH_X86_64),  # x86-64: skip the kill
        _insn(BPF_RET_K, 0, 0, SECCOMP_RET_KILL_PROCESS),
        _insn(BPF_LD_W_ABS, 0, 0, OFFSET_NR),
    ]
    checks = [X32_SYSCALL_BIT, *denied]
    n = len(checks)
    for i, nr in enumerate(checks):
        # jump forward to the shared "deny" (or "kill" for x32) return after the ALLOW
        to_end = n - i - 1
        if i == 0:
            body.append(_insn(BPF_JMP_JGE_K, to_end + 2, 0, nr))  # x32 -> kill (last insn)
        else:
            body.append(_insn(BPF_JMP_JEQ_K, to_end + 1, 0, nr))  # -> deny
    body += [
        _insn(BPF_RET_K, 0, 0, SECCOMP_RET_ALLOW),
        _insn(BPF_RET_K, 0, 0, deny_ret),
        _insn(BPF_RET_K, 0, 0, SECCOMP_RET_KILL_PROCESS),
    ]
    return b"".join(body)


class _SockFprog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]


def _install_filter(program: bytes) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    buf = ctypes.create_string_buffer(program)
    prog = _SockFprog(len(program) // 8, ctypes.cast(buf, ctypes.c_void_p))
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_NO_NEW_PRIVS) failed")
    if libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(prog), 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_SECCOMP) failed")


def confine(cpu_seconds: int, address_space_bytes: int) -> None:
    """Lock the current (child) process down. Linux x86-64 only; irreversible."""
    import resource  # Unix-only: imported here so the module loads on any platform

    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_AS, (address_space_bytes, address_space_bytes))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)  # a write fails with EFBIG instead
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (OPEN_FILES, OPEN_FILES))
    _install_filter(seccomp_program(sorted(DENIED_SYSCALLS.values())))
