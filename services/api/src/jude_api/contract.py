"""Export the OpenAPI 3.1 contract of record (XC-FND-06, IF-01).

    jude-openapi            write packages/contracts/openapi.json
    jude-openapi --check    exit 1 if the committed file differs from the code

The document is generated from the FastAPI app and serialised canonically (sorted keys,
two-space indent, UTF-8, trailing newline), so the same code always gives the same bytes.
Run from the repository root.
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from jude_api.main import create_app

DEFAULT_PATH = Path("packages/contracts/openapi.json")


def _never_called() -> None:
    return None


def openapi_document() -> dict[str, Any]:
    app = create_app(db_check=_never_called, readiness_checks={})
    doc: dict[str, Any] = app.openapi()
    return doc


def canonical_json(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jude-openapi", description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--check", action="store_true", help="fail if the file is out of date")
    args = parser.parse_args(argv)
    text = canonical_json(openapi_document())
    if args.check:
        current = args.path.read_text(encoding="utf-8") if args.path.exists() else ""
        if current != text:
            print(
                f"{args.path} is out of date with the API code. Regenerate it with "
                "`uv run jude-openapi` (and the client with `pnpm --filter @jude/contracts "
                "generate`), then commit both.",
                file=sys.stderr,
            )
            return 1
        print(f"{args.path}: up to date")
        return 0
    args.path.parent.mkdir(parents=True, exist_ok=True)
    args.path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
