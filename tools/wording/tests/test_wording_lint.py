"""UT-FN-OPS-01 / CI-FN-OPS-01: wording and localisation lint (TSK-OPS-01-C; VER-09).

Completion criterion: a seeded forbidden word or hard-coded string fails CI; the clean tree
passes. Seeds go into a copy of the scope in a temporary directory; the repository tree is not
modified.
"""

import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import ModuleType
from typing import Any
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load() -> ModuleType:
    path = ROOT / "tools/wording/wording_lint.py"
    spec = importlib.util.spec_from_file_location("wording_lint", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wording_lint"] = mod  # dataclasses resolve their module
    spec.loader.exec_module(mod)
    return mod


W = _load()
CONFIG: dict[str, Any] = W.load_config()


def run(root: Path, *paths: str, junit: Path | None = None) -> tuple[int, str]:
    import contextlib
    import io

    buf = io.StringIO()
    argv = ["--root", str(root), *paths, *(["--junit", str(junit)] if junit else [])]
    with contextlib.redirect_stdout(buf):
        code = W.main(argv)
    return code, buf.getvalue()


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A copy of the web app sources and the API messages: the clean tree in miniature."""
    for rel in ("apps/web/src", "services/api/src/jude_api/platform"):
        shutil.copytree(ROOT / rel, tmp_path / rel, ignore=shutil.ignore_patterns("__pycache__"))
    return tmp_path


def seed(root: Path, rel: str, text: str) -> str:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return rel


# --- completion criterion ---------------------------------------------------------------------


def test_completion_criterion_clean_tree_passes() -> None:
    code, out = run(ROOT)
    assert code == 0, out
    assert "0 hit(s)" in out


@pytest.mark.parametrize(
    ("rel", "text", "rule"),
    [
        ("apps/web/src/messages/ru.json", '{"x": "Данные анонимизированы"}', "WRD001"),
        ("services/api/src/jude_api/platform/messages_ru.json", '{"e": "Анонимизация"}', "WRD001"),
        ("apps/web/src/features/x/Panel.tsx", "export const P = () => <p>Severe case</p>;\n",
         "WRD001"),
        ("apps/web/src/features/x/Panel.tsx", "export const P = () => <p>Готово</p>;\n", "WRD002"),
        ("apps/web/src/features/x/Panel.tsx",
         'export const B = () => <button title="Сохранить" />;\n', "WRD002"),
        ("services/api/src/jude_api/domain/x.py", "CVAI_THRESHOLD = 3.5\n", "WRD003"),
        ("services/api/src/jude_api/domain/x.py", "flag = cvai > 3.5\n", "WRD003"),
    ],
)  # fmt: skip
def test_completion_criterion_seeded_hit_fails(tree: Path, rel: str, text: str, rule: str) -> None:
    assert run(tree)[0] == 0  # the copy is clean before the seed
    seed(tree, rel, text)
    code, out = run(tree)
    assert code == 1 and rule in out and rel in out, out


def test_junit_report(tree: Path, tmp_path: Path) -> None:
    seed(tree, "apps/web/src/features/x/P.tsx", "export const P = () => <p>Текст</p>;\n")
    report = tmp_path / "reports" / "wording.xml"
    assert run(tree, junit=report)[0] == 1
    suite = ET.parse(report).getroot()
    assert (suite.get("failures"), suite.find("testcase/failure") is not None) == ("1", True)


# --- WRD001: terms, inflections ---------------------------------------------------------------


@pytest.mark.parametrize("entry", CONFIG["terms"], ids=lambda e: e["id"])
def test_every_term_matches_its_forms_and_not_its_look_alikes(entry: dict[str, Any]) -> None:
    term = W.compile_term(entry)
    assert entry["source"].strip(), "every term names its documented source"
    for form in entry["forms"]:
        assert W.prohibited_words("f", f"Текст: {form}.", [term]), form
    for other in entry["not_forms"]:
        assert not W.prohibited_words("f", f"Текст: {other}.", [term]), other


def test_yo_is_folded_and_matching_is_whole_word() -> None:
    term = W.compile_term({"id": "t", "stem": "тёмн", "source": "test"})
    assert W.prohibited_words("f", "Тёмный и темнота", [term])
    assert not W.prohibited_words("f", "затемнение", [term])  # not a word start


def test_dec012_list_is_marked_pending_until_the_owner_provides_it() -> None:
    dec = CONFIG["dec012"]
    owner_terms = [t for t in CONFIG["terms"] if "DEC-012" in t["source"]]
    assert (dec["status"] == "pending") == (owner_terms == [])
    code, out = run(ROOT)
    assert code == 0 and ("DEC-012 word list is pending" in out) == (dec["status"] == "pending")


# --- WRD002: hard-coded UI strings -------------------------------------------------------------


@pytest.mark.parametrize(
    "good",
    [
        'export const P = () => <p>{t("home.heading")}</p>;',
        "export const P = () => <Box>{count}</Box>;",
        "// <p>Комментарий</p>\nexport const P = () => <br />;",
        "/* <p>Comment</p> */ export const P = () => <hr />;",
        'export const P = () => <a href="https://example.org">{t("k")}</a>;',
        "export const P = () => <p>   </p>;",
        'export const I = () => <img alt={t("logo")} src="/x.png" />;',
    ],
)
def test_resource_based_ui_passes(good: str) -> None:
    assert W.hardcoded_strings("P.tsx", good) == []


@pytest.mark.parametrize(
    "code",
    [
        "const [p, setP] = useState<string | null>(null);\n  async function f(e: E<F>) {}",
        'render(<LoginForm client={make("http://x")} onLoggedIn={f} />);\n  return { a };',
        'async function g(u: ReturnType<typeof x>, password = "s") {}',
        "const rows = list.map((r) => <Row key={r.id} />).filter(Boolean);",
    ],
)
def test_typescript_around_jsx_is_not_text(code: str) -> None:
    assert W.hardcoded_strings("P.tsx", code) == []


@pytest.mark.parametrize(
    "text",
    [
        "<p><br />Текст</p>",
        '<div style={{ color: "red" }}>Текст</div>',
        "<>Текст</>",
        '<Button variant="primary" onClick={() => go(1)}>Сохранить</Button>',
    ],
)
def test_jsx_text_in_every_tag_shape_is_found(text: str) -> None:
    assert [h.rule for h in W.hardcoded_strings("P.tsx", text)] == ["WRD002"]


def test_hardcoded_hit_names_the_line() -> None:
    hits = W.hardcoded_strings(
        "P.tsx", "export const P = () => (\n  <div>\n    Привет\n  </div>\n);\n"
    )
    assert [(h.rule, h.line) for h in hits] == [("WRD002", 3)]


# --- WRD003: threshold constants -----------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    ["CI_CUTOFF = 0.9", "severity_grade: float = 2", "export const NORMAL_RANGE_MAX = 85;",
     "if ci >= 90:", "return cvai<3.5"],
)  # fmt: skip
def test_threshold_constants_are_found(bad: str) -> None:
    assert W.threshold_constants("x.py", bad + "\n")


@pytest.mark.parametrize(
    "good",
    ["DET_TOLERANCE = '1e-9'", "MAX_FAILURES = 5", "threshold = config.get('x')",
     "ci = compute(a, b)", "if index > count:", "THRESHOLD_KEY = 'measure.threshold'"],
)  # fmt: skip
def test_non_classifying_code_passes(good: str) -> None:
    assert W.threshold_constants("x.py", good + "\n") == []


# --- exclusions and configuration ----------------------------------------------------------------


def test_excluded_paths_are_skipped_and_need_a_reason(tree: Path, tmp_path: Path) -> None:
    rel = seed(tree, "docs/user/register.md", "Ответ владельца: анонимизированы\n")
    assert run(tree)[0] == 1
    excl = tmp_path / "exclusions.txt"
    excl.write_text("docs/user/register.md  # owner answer quoted verbatim (NFR-06)\n", "utf-8")
    code, _ = W.main(["--root", str(tree), "--exclusions", str(excl)]), None
    assert code == 0 and rel
    excl.write_text("docs/user/register.md\n", "utf-8")
    assert W.main(["--root", str(tree), "--exclusions", str(excl)]) == 2


def test_wrong_schema_is_a_configuration_error(tmp_path: Path) -> None:
    bad = tmp_path / "terms.json"
    bad.write_text(json.dumps({**CONFIG, "schema": "x"}), "utf-8")
    assert W.main(["--terms", str(bad)]) == 2
