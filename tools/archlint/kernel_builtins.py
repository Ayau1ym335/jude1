"""Kernel purity check for builtins (XC-FND-04).

import-linter forbids I/O *modules* in jude_kernel and ruff bans numpy.random, but neither
sees builtins. This check fails on any reference to an I/O or dynamic-code builtin inside
the kernel sources (DEVELOPMENT_STANDARDS §5, contract IF-03).

Usage: python tools/archlint/kernel_builtins.py [PATH ...]   (default: packages/kernel/src)
Exit status: 0 clean, 1 violations found.
"""

import ast
from pathlib import Path
import sys

BANNED: dict[str, str] = {
    "open": "file I/O",
    "input": "console I/O",
    "print": "console I/O",
    "breakpoint": "debugger hook",
    "eval": "dynamic code",
    "exec": "dynamic code",
    "compile": "dynamic code",
    "__import__": "dynamic import bypasses import-linter",
}
DEFAULT_ROOT = Path("packages/kernel/src")


def violations(source: str, filename: str) -> list[str]:
    tree = ast.parse(source, filename=filename)
    found: list[str] = []
    for node in ast.walk(tree):
        name: str | None = None
        if isinstance(node, ast.Name) and node.id in BANNED:
            name = node.id
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "builtins"
            and node.attr in BANNED
        ):
            name = node.attr
        if name is not None and isinstance(node, ast.expr):
            found.append(
                f"{filename}:{node.lineno}:{node.col_offset + 1}: "
                f"KRN001 kernel must not use `{name}` ({BANNED[name]})"
            )
    return found


def iter_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        files.extend(sorted(p.rglob("*.py")) if p.is_dir() else [p])
    return files


def main(argv: list[str]) -> int:
    roots = [Path(a) for a in argv] or [DEFAULT_ROOT]
    found: list[str] = []
    for f in iter_files(roots):
        found.extend(violations(f.read_text(encoding="utf-8"), f.as_posix()))
    for line in found:
        sys.stdout.write(line + "\n")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
