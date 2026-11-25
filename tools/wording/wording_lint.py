"""Wording and localisation lint (FN-OPS-01, TSK-OPS-01-C; VER-09, NFR-05, NFR-06, FR-045, FR-111,
SEC-18, SAF-12, DATA-18).

Blocks merges that introduce prohibited words, severity terms, hard-coded UI strings or index
threshold constants. Three rules, each over its own scope (``terms.json``):

- WRD001 prohibited word: the terms of ``terms.json`` in any inflected form, in UI resources,
  report templates, manifest text, in-app help and user docs (NFR-06). Russian matching is
  by stem: a term's stem followed by any ending (ё folded to е, case-insensitive), so every
  inflection of the word is caught. Each term lists forms it must match and look-alike words it
  must not; the unit tests check both, so the lemma list stays honest.
- WRD002 hard-coded UI string: a JSX/TSX text node or a user-visible attribute (title, alt,
  placeholder, aria-label, label) with letters in it. UI text comes from the message resources
  (NFR-05), never from components.
- WRD003 threshold constant: product code that defines a threshold / cut-off / severity /
  grade / normal-range constant with a number, or compares an index (CI, CVA, CVAI, ...) with a
  number literal. The software never classifies (FR-045); clinic values are configuration
  (DEC-029).

``exclusions.txt`` lists the paths outside the scope. Examples are registers that must quote
owner answers verbatim, and quoted source titles (NFR-06). Every line needs a reason.

The DEC-012 word list is an owner decision and is not yet in the repository. ``terms.json``
marks it as pending, and the lint prints a notice until it is filled in. The terms the
repository already documents are enforced now.

Usage: python tools/wording/wording_lint.py [--root DIR] [--junit FILE] [PATH ...]
Exit status: 0 clean, 1 hits (merge blocked), 2 configuration error.
"""

import argparse
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
import fnmatch
import json
from pathlib import Path
import re
import sys
from typing import Any
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
TERMS = HERE / "terms.json"
EXCLUSIONS = HERE / "exclusions.txt"
LETTER = r"A-Za-zА-Яа-яЁё"


@dataclass(frozen=True)
class Hit:
    rule: str
    path: str
    line: int
    text: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} {self.detail}: {self.text.strip()[:120]}"


@dataclass(frozen=True)
class Term:
    id: str
    pattern: re.Pattern[str]
    source: str
    use_instead: str


def fold(text: str) -> str:
    return text.replace("ё", "е").replace("Ё", "Е")


def compile_term(entry: dict[str, Any]) -> Term:
    """``stem``: the stem plus any word ending. ``words``: whole words only (English phrases)."""
    if "stem" in entry:
        body = re.escape(fold(entry["stem"])) + r"\w*"
    else:
        body = (
            "(?:"
            + "|".join(re.escape(fold(w)).replace(r"\ ", r"\s+") for w in entry["words"])
            + r")"
        )
    pattern = re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)
    return Term(entry["id"], pattern, entry["source"], entry.get("use_instead", ""))


def load_config(path: Path = TERMS) -> dict[str, Any]:
    config: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "wording-terms/1":
        raise ValueError(f"{path}: schema must be wording-terms/1")
    return config


def load_exclusions(path: Path = EXCLUSIONS) -> list[str]:
    globs = []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        glob, sep, reason = line.partition("#")
        if not sep or not reason.strip():
            raise ValueError(f"{path}:{n}: every exclusion needs a reason after '#'")
        globs.append(glob.strip())
    return globs


def matches(rel: str, globs: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(rel, g) for g in globs)


def files(
    root: Path, globs: list[str], excluded: list[str], only: set[str] | None
) -> Iterator[str]:
    seen: set[str] = set()
    for g in globs:
        for p in sorted(root.glob(g)):
            rel = p.relative_to(root).as_posix()
            if (
                p.is_file()
                and rel not in seen
                and "node_modules" not in p.parts
                and not matches(rel, excluded)
                and (only is None or rel in only)
            ):
                seen.add(rel)
                yield rel


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# --- WRD001 -----------------------------------------------------------------------------------


def prohibited_words(rel: str, text: str, terms: list[Term]) -> list[Hit]:
    folded = fold(text)
    hits = []
    for term in terms:
        for m in term.pattern.finditer(folded):
            hint = f" (use: {term.use_instead})" if term.use_instead else ""
            n = line_of(folded, m.start())
            detail = f"prohibited word {m.group(0)!r} [{term.id}; {term.source}]{hint}"
            hits.append(Hit("WRD001", rel, n, text.splitlines()[n - 1], detail))
    return hits


# --- WRD002 -----------------------------------------------------------------------------------

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?m)(?<![:\"'])//.*$")
# A JSX tag: a name, then attributes in JSX syntax (name, name="..", name='..', name={..} with
# one level of nested braces), then > or />. TypeScript generics such as useState<string | null>
# do not fit this grammar, so the code after them is never mistaken for JSX text.
_ATTR_VALUE = r"""(?:"[^"]*"|'[^']*'|\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})"""
_JSX_TAG = rf"<(?:/?[A-Za-z][\w.:-]*(?:\s+[A-Za-z_:][\w:.-]*(?:\s*=\s*{_ATTR_VALUE})?)*\s*/?)?>"
_TEXT_NODE = re.compile(rf"({_JSX_TAG})([^<>{{}}]*[{LETTER}][^<>{{}}]*)(?=<|{{)")
_ATTRIBUTE = re.compile(
    rf"\b(title|alt|placeholder|aria-label|label)\s*=\s*([\"'])([^\"']*[{LETTER}][^\"']*)\2"
)


def _blank(m: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", m.group(0))  # keep offsets and line numbers


def _looks_like_code(candidate: str) -> bool:
    """TypeScript after a tag-like token, not JSX text: statement or argument punctuation.

    UI text in a component practically never contains ';' or '=', nor starts with ')', ']',
    ',' or '.'; code after a self-closing element (``<X />);``) or after a type argument
    (``ReturnType<typeof x>, p = 1``) always does. A rare text like that is missed, never
    falsely reported.
    """
    stripped = candidate.lstrip()
    return ";" in candidate or "=" in candidate or stripped[:1] in {")", "]", ",", "."}


def hardcoded_strings(rel: str, text: str) -> list[Hit]:
    code = _LINE_COMMENT.sub(_blank, _BLOCK_COMMENT.sub(_blank, text))
    lines = text.splitlines()
    hits = []
    for m in _TEXT_NODE.finditer(code):
        if _looks_like_code(m.group(2)):
            continue
        n = line_of(code, m.start(2) + len(m.group(2)) - len(m.group(2).lstrip()))
        detail = f"hard-coded JSX text {m.group(2).strip()!r}; use the message resources"
        hits.append(Hit("WRD002", rel, n, lines[n - 1], detail))
    for m in _ATTRIBUTE.finditer(code):
        n = line_of(code, m.start())
        detail = f"hard-coded {m.group(1)}={m.group(3)!r}; use the message resources"
        hits.append(Hit("WRD002", rel, n, lines[n - 1], detail))
    return hits


# --- WRD003 -----------------------------------------------------------------------------------

_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_CLASSIFYING_NAME = re.compile(
    rf"(?im)^\s*(?:export\s+)?(?:const\s+|let\s+|var\s+)?"
    rf"(\w*(?:threshold|cutoff|cut_off|severity|severe|grade|normal_range|abnormal)\w*)"
    rf"\s*(?::[^=\n]+)?=\s*({_NUMBER})\b"
)
_INDEX_COMPARISON = re.compile(
    rf"(?i)(?<![\w.])(ci|cva|cvai|cr|ri|cephalic_index|cranial_index|cranial_vault_asymmetry"
    rf"(?:_index)?)\s*(<=|>=|<|>)\s*({_NUMBER})\b"
)


def threshold_constants(rel: str, text: str) -> list[Hit]:
    lines = text.splitlines()
    hits = []
    for m in _CLASSIFYING_NAME.finditer(text):
        n = line_of(text, m.start(1))
        detail = f"classifying constant {m.group(1)} = {m.group(2)} (FR-045, DEC-029)"
        hits.append(Hit("WRD003", rel, n, lines[n - 1], detail))
    for m in _INDEX_COMPARISON.finditer(text):
        n = line_of(text, m.start())
        detail = f"index {m.group(1)} compared with a constant (FR-045)"
        hits.append(Hit("WRD003", rel, n, lines[n - 1], detail))
    return hits


# --- driver -----------------------------------------------------------------------------------


def lint(root: Path, config: dict[str, Any], excluded: list[str],
         only: set[str] | None = None) -> list[Hit]:  # fmt: skip
    terms = [compile_term(e) for e in config["terms"]]
    scope = config["scope"]
    hits: list[Hit] = []
    for rel in files(root, scope["words"], excluded, only):
        hits += prohibited_words(rel, (root / rel).read_text(encoding="utf-8"), terms)
    for rel in files(root, scope["ui_components"], excluded, only):
        hits += hardcoded_strings(rel, (root / rel).read_text(encoding="utf-8"))
    for rel in files(root, scope["code"], excluded, only):
        hits += threshold_constants(rel, (root / rel).read_text(encoding="utf-8"))
    return sorted(hits, key=lambda h: (h.path, h.line, h.rule, h.detail))


def write_junit(path: Path, hits: list[Hit]) -> None:
    suite = ET.Element("testsuite", name="wording", tests=str(max(len(hits), 1)),
                       failures=str(len(hits)))  # fmt: skip
    if not hits:
        ET.SubElement(suite, "testcase", classname="wording", name="clean tree")
    for h in hits:
        case = ET.SubElement(suite, "testcase", classname=h.rule, name=f"{h.path}:{h.line}")
        ET.SubElement(case, "failure", message=h.detail).text = str(h)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wording_lint")
    parser.add_argument("paths", nargs="*", help="limit to these files (relative to --root)")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--terms", type=Path, default=TERMS)
    parser.add_argument("--exclusions", type=Path, default=EXCLUSIONS)
    args = parser.parse_args(argv)
    try:
        config = load_config(args.terms)
        excluded = load_exclusions(args.exclusions)
    except (OSError, ValueError, KeyError) as exc:
        sys.stderr.write(f"wording lint: configuration error: {exc}\n")
        return 2
    only = {Path(p).as_posix() for p in args.paths} or None
    hits = lint(args.root.resolve(), config, excluded, only)
    out = sys.stdout
    if hasattr(out, "reconfigure"):
        out.reconfigure(encoding="utf-8")  # Cyrillic on Windows consoles too
    for h in hits:
        out.write(f"{h}\n")
    if config.get("dec012", {}).get("status") == "pending":
        out.write("wording lint: notice: the DEC-012 word list is pending the owner "
                  "(tools/wording/terms.json); documented terms are enforced.\n")  # fmt: skip
    if args.junit:
        write_junit(args.junit, hits)
    out.write(f"wording lint: {len(hits)} hit(s)\n")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
