"""Seeded-violation self-test for the lint gates (XC-FND-04 completion criterion).

Every rule is exercised twice: a seeded violation must make the tool exit non-zero and name
the expected rule, and a clean counterpart must pass. The pair proves the failure comes from
the rule, not from a broken tool. Nothing in the repository tree is modified: code goes in
via stdin, ``-c`` or a temporary directory.

Run: uv run pytest -m lint_selftest   (needs `uv sync` and `pnpm install`)
"""

from collections.abc import Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.lint_selftest

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "apps" / "web"
PY = sys.executable
TIMEOUT_S = 180


def node_bin(*parts: str) -> list[str]:
    script = ROOT.joinpath(*parts)
    if not script.exists():
        pytest.fail(f"{script} missing: run `pnpm install` first")
    node = shutil.which("node")
    assert node is not None, "node not on PATH"
    return [node, str(script)]


def run(
    argv: Sequence[str],
    *,
    cwd: Path = ROOT,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    # stdin goes as bytes: text mode would turn "\n" into CRLF on Windows.
    proc = subprocess.run(
        list(argv),
        cwd=cwd,
        input=None if stdin is None else stdin.encode("utf-8"),
        capture_output=True,
        timeout=TIMEOUT_S,
        env={**os.environ, **(env or {})},
        check=False,
    )
    return subprocess.CompletedProcess(
        proc.args,
        proc.returncode,
        proc.stdout.decode("utf-8", errors="replace"),
        proc.stderr.decode("utf-8", errors="replace"),
    )


def write(path: Path, text: str) -> Path:
    """Write with LF line endings on every OS (the gates require LF)."""
    path.write_bytes(text.encode("utf-8"))
    return path


def assert_gate(
    bad: subprocess.CompletedProcess[str], good: subprocess.CompletedProcess[str], expect: str
) -> None:
    out = bad.stdout + bad.stderr
    assert bad.returncode != 0, f"seeded violation passed the gate:\n{out}"
    assert expect in out, f"expected {expect!r} in tool output:\n{out}"
    assert good.returncode == 0, f"clean counterpart failed:\n{good.stdout}{good.stderr}"


# --- ruff (lint, format, kernel-only bans) -----------------------------------------------


@dataclass(frozen=True)
class RuffCase:
    id: str
    path: str
    bad: str
    good: str
    expect: str


RUFF_CASES = [
    RuffCase(
        "unused-import",
        "services/api/src/jude_api/_seed.py",
        "import os\n",
        "import os\n\nCWD = os.sep\n",
        "F401",
    ),
    RuffCase(
        "line-length-100",
        "services/api/src/jude_api/_seed.py",
        f"X = '{'a' * 100}'\n",
        "X = 'a'\n",
        "E501",
    ),
    RuffCase(
        "security-bind-all",
        "services/worker/src/jude_worker/_seed.py",
        'HOST = "0.0.0.0"\n',
        'HOST = "127.0.0.1"\n',
        "S104",
    ),
    RuffCase(
        "kernel-numpy-random",
        "packages/kernel/src/jude_kernel/_seed.py",
        "from numpy import random\n\nR = random\n",
        "import numpy\n\nN = numpy\n",
        "TID251",
    ),
    RuffCase(
        "kernel-print", "packages/kernel/src/jude_kernel/_seed.py", "print(1)\n", "X = 1\n", "T201"
    ),
]


@pytest.mark.parametrize("case", RUFF_CASES, ids=lambda c: c.id)
def test_ruff_rule(case: RuffCase) -> None:
    argv = [PY, "-m", "ruff", "check", "--no-cache", "--stdin-filename", case.path, "-"]
    assert_gate(run(argv, stdin=case.bad), run(argv, stdin=case.good), case.expect)


def test_ruff_format() -> None:
    argv = [
        PY,
        "-m",
        "ruff",
        "format",
        "--diff",
        "--no-cache",
        "--stdin-filename",
        "services/api/src/jude_api/_seed.py",
        "-",
    ]
    assert_gate(run(argv, stdin="x=1\n"), run(argv, stdin="x = 1\n"), "+x = 1")


# --- mypy --strict -------------------------------------------------------------------------


def test_mypy_strict(tmp_path: Path) -> None:
    # Explicit file arguments replace the `files` list from pyproject.toml; strictness stays.
    argv = [PY, "-m", "mypy", "--config-file", "pyproject.toml", "--no-incremental"]
    bad = run([*argv, str(write(tmp_path / "bad.py", "def f(x):\n    return x\n"))])
    good = run([*argv, str(write(tmp_path / "good.py", "def f(x: int) -> int:\n    return x\n"))])
    assert_gate(bad, good, "no-untyped-def")


# --- kernel builtins (archlint) --------------------------------------------------------------


@pytest.mark.parametrize("call", ["open('x')", "print(1)", "exec('1')", "__import__('os')"])
def test_kernel_builtins(tmp_path: Path, call: str) -> None:
    bad = write(tmp_path / "bad.py", f"X = {call}\n")
    good = write(tmp_path / "good.py", "X = 1\n")
    script = str(ROOT / "tools" / "archlint" / "kernel_builtins.py")
    assert_gate(run([PY, script, str(bad)]), run([PY, script, str(good)]), "KRN001")


# --- import-linter layer contracts -----------------------------------------------------------

SRC_DIRS = {
    "jude_kernel": "packages/kernel/src",
    "jude_api": "services/api/src",
    "jude_worker": "services/worker/src",
    "jude_storage_fake": "tools/storage_fake/src",
}


def _import_tree(dest: Path, seed: tuple[str, str] | None) -> subprocess.CompletedProcess[str]:
    """Copy the four packages to dest, optionally add a seeded module, run lint-imports there."""
    paths = []
    for pkg, src in SRC_DIRS.items():
        target = dest / src
        shutil.copytree(
            ROOT / src / pkg, target / pkg, ignore=shutil.ignore_patterns("__pycache__")
        )
        paths.append(str(target))
    if seed is not None:
        pkg, code = seed
        write(dest / SRC_DIRS[pkg] / pkg / "_seed.py", code)
    shutil.copy(ROOT / "pyproject.toml", dest / "pyproject.toml")
    return run(
        [
            PY,
            "-c",
            "from importlinter.cli import lint_imports_command; lint_imports_command()",
            "--config",
            "pyproject.toml",
            "--no-cache",
        ],
        cwd=dest,
        env={"PYTHONPATH": os.pathsep.join(paths)},
    )


@pytest.mark.parametrize(
    ("seed", "contract"),
    [
        (("jude_kernel", "import os\n"), "Kernel is pure"),
        (("jude_kernel", "import time\n"), "Kernel is pure"),
        (("jude_kernel", "import importlib\n"), "Kernel is pure"),
        (("jude_kernel", "import jude_api\n"), "Kernel does not depend on services"),
        (("jude_api", "import jude_storage_fake\n"), "never import the dev-only storage fake"),
        (("jude_api", "import jude_worker\n"), "API and worker talk only"),
    ],
    ids=[
        "kernel-os",
        "kernel-time",
        "kernel-importlib",
        "kernel-imports-api",
        "api-imports-fake",
        "api-imports-worker",
    ],
)
def test_import_contract(tmp_path: Path, seed: tuple[str, str], contract: str) -> None:
    bad = _import_tree(tmp_path / "bad", seed)
    good = _import_tree(tmp_path / "good", None)
    assert_gate(bad, good, contract)
    assert "BROKEN" in bad.stdout


# --- web: eslint, prettier, tsc --------------------------------------------------------------


@pytest.mark.parametrize(
    ("bad", "good", "expect"),
    [
        (
            'import k from "../../../../packages/kernel/src/jude_kernel";\nexport default k;\n',
            'import { useState } from "react";\nexport default useState;\n',
            "no-restricted-imports",
        ),
        ("export const x: any = 1;\n", "export const x: number = 1;\n", "no-explicit-any"),
    ],
    ids=["ui-imports-kernel", "explicit-any"],
)
def test_eslint_rule(bad: str, good: str, expect: str) -> None:
    argv = [
        *node_bin("apps", "web", "node_modules", "eslint", "bin", "eslint.js"),
        "--max-warnings=0",
        "--stdin",
        "--stdin-filename",
        "src/features/_seed.ts",
    ]
    assert_gate(run(argv, cwd=WEB, stdin=bad), run(argv, cwd=WEB, stdin=good), expect)


def test_prettier(tmp_path: Path) -> None:
    bad = write(tmp_path / "bad.ts", "const  a={b:1}\nexport default a\n")
    good = write(tmp_path / "good.ts", "const a = { b: 1 };\nexport default a;\n")
    argv = [
        *node_bin("apps", "web", "node_modules", "prettier", "bin", "prettier.cjs"),
        "--config",
        str(WEB / ".prettierrc.json"),
        "--check",
    ]
    assert_gate(run([*argv, str(bad)]), run([*argv, str(good)]), "bad.ts")


def _tsc(dest: Path, code: str) -> subprocess.CompletedProcess[str]:
    dest.mkdir()
    write(dest / "seed.ts", code)
    write(
        dest / "tsconfig.json",
        json.dumps(
            {
                "extends": (WEB / "tsconfig.json").as_posix(),
                "compilerOptions": {"types": [], "plugins": [], "incremental": False},
                "files": ["seed.ts"],
                "include": [],
            }
        ),
    )
    tsc = node_bin("apps", "web", "node_modules", "typescript", "bin", "tsc")
    return run([*tsc, "--noEmit", "-p", str(dest / "tsconfig.json")])


def test_tsc_strict(tmp_path: Path) -> None:
    bad = _tsc(tmp_path / "bad", "export function f(a) {\n  return a;\n}\n")
    good = _tsc(tmp_path / "good", "export function f(a: number): number {\n  return a;\n}\n")
    assert_gate(bad, good, "TS7006")


# --- commitlint ------------------------------------------------------------------------------

GOOD_COMMIT = "feat(api): add health endpoint\n\nTask: XC-FND-02\n"


@pytest.mark.parametrize(
    ("message", "expect"),
    [
        ("added stuff\n\nTask: XC-FND-02\n", "type-empty"),
        ("feat(api): add health endpoint\n", "task-trailer"),
        ("feat(api): add health endpoint\n\nTask: XC-FND-99\n", "not an ID"),
        (
            "feat(api): add health endpoint\n\nTask: XC-FND-02\nTask: XC-FND-04\n",
            "exactly one Task",
        ),
    ],
    ids=["not-conventional", "no-trailer", "unknown-task", "two-tasks"],
)
def test_commitlint(message: str, expect: str) -> None:
    argv = node_bin("node_modules", "@commitlint", "cli", "cli.js")
    assert_gate(run(argv, stdin=message), run(argv, stdin=GOOD_COMMIT), expect)


# --- wording / localisation lint (FN-OPS-01, VER-09) ---------------------------------------------

WORDING = ROOT / "tools" / "wording" / "wording_lint.py"


@pytest.mark.parametrize(
    ("rel", "bad", "good", "expect"),
    [
        ("apps/web/src/messages/ru.json", '{"k": "Данные анонимизированы"}',
         '{"k": "Данные без прямых идентификаторов"}', "WRD001"),
        ("apps/web/src/features/x/P.tsx", "export const P = () => <p>Сохранить</p>;\n",
         'export const P = () => <p>{t("save")}</p>;\n', "WRD002"),
        ("services/api/src/jude_api/x.py", "CVAI_THRESHOLD = 3.5\n",
         "CVAI_KEY = 'measure.cvai'\n", "WRD003"),
    ],
    ids=["prohibited-word", "hardcoded-ui-text", "threshold-constant"],
)  # fmt: skip
def test_wording_lint(tmp_path: Path, rel: str, bad: str, good: str, expect: str) -> None:
    results = []
    for name, text in (("bad", bad), ("good", good)):
        root = tmp_path / name
        (root / rel).parent.mkdir(parents=True)
        write(root / rel, text)
        results.append(run([PY, str(WORDING), "--root", str(root)]))
    assert_gate(results[0], results[1], expect)
