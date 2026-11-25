"""Licence allow-list check and SOUP list (FN-OPS-02, TSK-OPS-02-C; SEC-09, ADR-011, TD-23).

Ship only allow-listed licences, and generate the SOUP list (05 §4.4).

**What is shipped.**
- Python: the locked, non-dev dependency closure of each shipped image package (``jude-api``,
  ``jude-worker``), from ``uv export --no-dev``. The images install exactly this with
  ``uv sync --no-dev --package``. Lockfile environment markers are evaluated for the image
  target (linux/amd64, CPython 3.12, IDR-09), so e.g. Windows-only tzdata is not shipped.
  Dev and oracle groups (trimesh, CGAL, ... are oracle-only, TD-03) are not shipped.
- npm: the production closure of ``@jude/web`` (``pnpm licenses list --prod``).

**Licence of a package.** Python takes the ``License-Expression`` (PEP 639), else the
``License`` field when it is a valid SPDX expression of known ids. npm takes the ``license``
field. A non-SPDX declaration (e.g. numba's "BSD") needs an entry in ``licence_overrides``
naming the verified licence and its source.

**Decision.** An SPDX expression is allowed when it evaluates to true, with ``OR`` meaning
any and ``AND`` meaning all. An id passes when it is on the allow-list; ``X WITH e`` passes
when X is allowed and e is a listed exception (exceptions only add permissions). A package
outside that needs a ``package_exceptions`` entry pinned to its exact licence. Anything else
fails the build:
- GPL or AGPL;
- a missing or unparsable licence;
- a licence that is not on the list.

**Output.** The SOUP list as CSV (ecosystem, component, name, version, licence, supplier,
basis). It is sorted and deterministic. The supplier is the author or maintainer name; e-mail
addresses are stripped.

Usage:
  python tools/licences/licence_check.py [--soup reports/soup.csv]
  python tools/licences/licence_check.py --dump-inventory inv.json   (collect only)
  python tools/licences/licence_check.py --inventory inv.json         (check a given inventory)
Environment: JUDE_PNPM overrides the pnpm command (default "pnpm").
Exit status: 0 allowed, 1 violation (merge blocked), 2 configuration or collection error.
"""

import argparse
from collections.abc import Iterable, Iterator, Sequence
import csv
from dataclasses import asdict, dataclass
import importlib.metadata as md
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any, Final

from packaging.markers import Marker

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
POLICY = HERE / "policy.json"
SHIPPED_PYTHON = ("jude-api", "jude-worker")
SHIPPED_NPM = ("@jude/web",)


@dataclass(frozen=True)
class Package:
    ecosystem: str  # pypi | npm
    component: str  # the shipped package it belongs to
    name: str
    version: str
    licence: str  # SPDX expression as declared (or "" when none)
    supplier: str


@dataclass(frozen=True)
class Verdict:
    package: Package
    licence: str  # the expression that was judged
    basis: str  # allow-list | exception | override+allow-list
    ok: bool
    reason: str


# --- SPDX expressions ---------------------------------------------------------------------------

_TOKEN = re.compile(r"\s*(\(|\)|[A-Za-z0-9.+-]+)")


def _tokens(expr: str) -> list[str]:
    pos, out = 0, []
    expr = expr.strip()
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            raise ValueError(f"not an SPDX expression: {expr!r}")
        out.append(m.group(1))
        pos = m.end()
        while pos < len(expr) and expr[pos].isspace():
            pos += 1
    return out


def spdx_allowed(expr: str, allowed: Iterable[str], exceptions: Iterable[str]) -> bool:
    """Evaluate an SPDX expression against the allow-list (ids compared case-insensitively)."""
    ok_ids = {a.lower() for a in allowed}
    ok_exc = {e.lower() for e in exceptions}
    toks = _tokens(expr)
    if not toks:
        raise ValueError("empty licence expression")
    pos = 0

    def peek() -> str | None:
        return toks[pos] if pos < len(toks) else None

    def take() -> str:
        nonlocal pos
        if pos >= len(toks):
            raise ValueError(f"incomplete SPDX expression: {expr!r}")
        pos += 1
        return toks[pos - 1]

    def primary() -> bool:
        tok = take()
        if tok == "(":
            value = disjunction()
            if take() != ")":
                raise ValueError(f"unbalanced parentheses: {expr!r}")
            return value
        if tok.upper() in {"AND", "OR", "WITH", ")"}:
            raise ValueError(f"unexpected {tok!r} in {expr!r}")
        licence_ok = tok.lower() in ok_ids
        if (peek() or "").upper() == "WITH":
            take()
            exc = take()
            return licence_ok and exc.lower() in ok_exc
        return licence_ok

    def conjunction() -> bool:
        value = primary()
        while (peek() or "").upper() == "AND":
            take()
            value = primary() and value  # evaluate both sides: syntax errors surface
        return value

    def disjunction() -> bool:
        value = conjunction()
        while (peek() or "").upper() == "OR":
            take()
            value = conjunction() or value
        return value

    result = disjunction()
    if pos != len(toks):
        raise ValueError(f"trailing tokens in {expr!r}")
    return result


# --- policy -------------------------------------------------------------------------------------


def load_policy(path: Path = POLICY) -> dict[str, Any]:
    policy: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("schema") != "licence-policy/1":
        raise ValueError(f"{path}: schema must be licence-policy/1")
    for entry in policy.get("package_exceptions", []):
        if not entry.get("reason", "").strip():
            raise ValueError(f"{path}: exception for {entry.get('name')} needs a reason")
    return policy


def judge(pkg: Package, policy: dict[str, Any]) -> Verdict:
    licence, basis = pkg.licence, "allow-list"
    for o in policy.get("licence_overrides", []):
        if (o["ecosystem"], o["name"]) == (pkg.ecosystem, pkg.name) and o["declared"] == licence:
            licence, basis = o["licence"], "override+allow-list"
    for e in policy.get("package_exceptions", []):
        if (e["ecosystem"], e["name"]) == (pkg.ecosystem, pkg.name):
            if e["licence"] == licence:
                return Verdict(pkg, licence, "exception", True, e["reason"])
            return Verdict(
                pkg,
                licence,
                "exception",
                False,
                f"exception covers {e['licence']!r}, package now declares {licence!r}",
            )
    if not licence.strip():
        return Verdict(pkg, licence, basis, False, "no licence declared")
    try:
        ok = spdx_allowed(licence, policy["allowed"], policy.get("allowed_with_exceptions", []))
    except ValueError as exc:
        return Verdict(pkg, licence, basis, False, f"{exc} (add a licence_overrides entry)")
    return Verdict(pkg, licence, basis, ok, "" if ok else "licence not on the allow-list")


# --- collection ---------------------------------------------------------------------------------

_EMAIL = re.compile(r"\s*<?[\w.+-]+@[\w-]+(\.[\w-]+)+>?\s*,?")


def supplier_name(*candidates: str | None) -> str:
    for c in candidates:
        name = _EMAIL.sub(" ", c or "").strip(" ,")
        if name:
            return " ".join(name.split())
    return ""


def _run(cmd: Sequence[str]) -> str:
    program = shutil.which(cmd[0]) or cmd[0]  # npx.cmd / pnpm.cmd on Windows
    proc = subprocess.run([program, *cmd[1:]], cwd=ROOT, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {proc.stderr.decode(errors='replace')[:400]}")
    return proc.stdout.decode("utf-8")


# The shipped images: linux/amd64, CPython 3.12 (IDR-09). Environment markers of the universal
# lockfile are evaluated for this target, not for the machine running the check.
IMAGE_TARGET: Final = {
    "sys_platform": "linux", "platform_system": "Linux", "platform_machine": "x86_64",
    "os_name": "posix", "implementation_name": "cpython",
    "platform_python_implementation": "CPython", "python_version": "3.12",
    "python_full_version": "3.12.0",
}  # fmt: skip


def parse_export(text: str) -> list[tuple[str, str]]:
    """(name, version) of every requirement of ``uv export`` that applies to the image target."""
    found = []
    for raw in text.splitlines():
        spec, _, marker = raw.partition(";")
        spec = spec.strip()
        if not spec or spec.startswith(("#", "-")) or "==" not in spec:
            continue
        if marker.strip() and not Marker(marker.strip()).evaluate(dict(IMAGE_TARGET)):
            continue  # e.g. tzdata ; sys_platform == 'win32' is not in a linux image
        name, version = (s.strip() for s in spec.split("==", 1))
        found.append((name, version))
    return found


def python_packages() -> Iterator[Package]:
    for component in SHIPPED_PYTHON:
        text = _run(
            [
                "uv",
                "export",
                "--frozen",
                "--no-dev",
                "--no-hashes",
                "--no-emit-workspace",
                "--package",
                component,
                "--format",
                "requirements.txt",
            ]
        )
        for name, version in parse_export(text):
            try:
                meta = md.metadata(name)
            except md.PackageNotFoundError as exc:
                raise RuntimeError(f"{name} is locked but not installed: run `uv sync`") from exc
            if meta["Version"] != version:
                raise RuntimeError(f"{name}: installed {meta['Version']}, locked {version}")
            licence = meta.get("License-Expression") or (meta.get("License") or "").strip()
            supplier = supplier_name(
                meta.get("Author"),
                meta.get("Author-email"),
                meta.get("Maintainer"),
                meta.get("Maintainer-email"),
            )
            yield Package("pypi", component, name.lower(), version, licence, supplier)


def npm_packages() -> Iterator[Package]:
    pnpm = shlex.split(os.environ.get("JUDE_PNPM", "pnpm"))
    for component in SHIPPED_NPM:
        data = json.loads(
            _run([*pnpm, "licenses", "list", "--prod", "--json", "--filter", component])
        )
        for licence, entries in data.items():
            for e in entries:
                author = e.get("author")
                name = author.get("name") if isinstance(author, dict) else author
                for version in e.get("versions") or [e.get("version", "")]:
                    yield Package(
                        "npm",
                        component,
                        e["name"],
                        version,
                        "" if licence == "Unknown" else licence,
                        supplier_name(name, e.get("homepage")),
                    )


def collect() -> list[Package]:
    return sorted({*python_packages(), *npm_packages()}, key=_key)


def _key(p: Package) -> tuple[str, ...]:
    return (p.ecosystem, p.component, p.name, p.version)


# --- output -------------------------------------------------------------------------------------


def soup_csv(verdicts: Sequence[Verdict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["ecosystem", "component", "name", "version", "licence", "supplier", "basis"])
    for v in sorted(verdicts, key=lambda v: _key(v.package)):
        p = v.package
        w.writerow([p.ecosystem, p.component, p.name, p.version, v.licence, p.supplier, v.basis])
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="licence_check")
    parser.add_argument("--policy", type=Path, default=POLICY)
    parser.add_argument("--inventory", type=Path, help="check this inventory instead of collecting")
    parser.add_argument("--dump-inventory", type=Path, help="write the collected inventory")
    parser.add_argument("--soup", type=Path, help="write the SOUP list (CSV)")
    args = parser.parse_args(argv)
    out = sys.stdout
    if hasattr(out, "reconfigure"):
        out.reconfigure(encoding="utf-8")
    try:
        policy = load_policy(args.policy)
        if args.inventory:
            raw = json.loads(args.inventory.read_text(encoding="utf-8"))
            packages = sorted((Package(**p) for p in raw), key=_key)
        else:
            packages = collect()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        sys.stderr.write(f"licence check: {exc}\n")
        return 2
    if args.dump_inventory:
        args.dump_inventory.write_text(
            json.dumps([asdict(p) for p in packages], indent=1) + "\n", encoding="utf-8"
        )
        return 0
    verdicts = [judge(p, policy) for p in packages]
    for v in verdicts:
        if not v.ok:
            p = v.package
            out.write(
                f"LIC001 {p.ecosystem}:{p.name}=={p.version} ({p.component}): "
                f"{v.licence or '<none>'}: {v.reason}\n"
            )
    if args.soup:
        args.soup.parent.mkdir(parents=True, exist_ok=True)
        args.soup.write_text(soup_csv(verdicts), encoding="utf-8", newline="\n")
    bad = sum(not v.ok for v in verdicts)
    out.write(
        f"licence check: {len(verdicts)} shipped packages, {bad} violation(s); "
        f"policy {policy['status'].split(';')[0]}\n"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
