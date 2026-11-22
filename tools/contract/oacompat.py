"""Breaking-change check for the OpenAPI contract (XC-FND-06, IF-01: additive only within v1).

    python tools/contract/oacompat.py OLD.json NEW.json
    python tools/contract/oacompat.py --base-ref <git ref> [NEW.json]

Exit 0 if NEW is backward compatible with OLD, 1 if it breaks clients, 2 on usage errors.
With --base-ref, OLD is NEW's path at that git ref; if the file does not exist there yet, there
is nothing to break and the check passes.

Rules. Requests (client -> server) must accept everything they accepted before; responses
(server -> client) must not send anything they did not promise before:

| Area | Breaking |
|---|---|
| Paths, operations | a path or a method removed |
| Parameters | removed; new required; optional -> required; schema narrowed (request rules) |
| Request body | new required body; optional -> required; media type removed; schema narrowed |
| Request schema | type narrowed; enum value removed (or enum added); new required property; |
|                | property removed while extra properties are forbidden; extra properties newly |
|                | forbidden; max* lowered / min* raised / pattern or format added or changed |
| Responses | a status code removed; a media type removed |
| Response schema | type widened (incl. becoming nullable); enum value added (or enum removed); |
|                 | property removed; required property becomes optional; format changed |

Adding paths, operations, optional parameters, optional request fields, response fields and
status codes is allowed. A breaking change needs a new major version (/api/v2, IF-01).
"""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

Schema = dict[str, Any]
Doc = dict[str, Any]

METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")
UPPER_BOUNDS = ("maxLength", "maximum", "exclusiveMaximum", "maxItems", "maxProperties")
LOWER_BOUNDS = ("minLength", "minimum", "exclusiveMinimum", "minItems", "minProperties")


@dataclass(frozen=True)
class Finding:
    location: str
    message: str

    def __str__(self) -> str:
        return f"BREAKING {self.location}: {self.message}"


class Checker:
    def __init__(self, old: Doc, new: Doc) -> None:
        self.old, self.new = old, new
        self.findings: list[Finding] = []
        self._seen: set[tuple[str, str, str]] = set()

    # -- helpers ---------------------------------------------------------------------------
    def _flag(self, loc: str, msg: str) -> None:
        self.findings.append(Finding(loc, msg))

    @staticmethod
    def _resolve(doc: Doc, schema: Schema | None) -> Schema:
        seen = 0
        while isinstance(schema, dict) and "$ref" in schema and seen < 64:
            ref = schema["$ref"]
            if not ref.startswith("#/"):
                raise ValueError(f"external $ref not supported: {ref}")
            node: Any = doc
            for part in ref[2:].split("/"):
                node = node[part.replace("~1", "/").replace("~0", "~")]
            schema = node
            seen += 1
        return schema if isinstance(schema, dict) else {}

    def _types(self, doc: Doc, schema: Schema) -> set[str]:
        s = self._resolve(doc, schema)
        variants = s.get("anyOf") or s.get("oneOf")
        if variants:
            out: set[str] = set()
            for v in variants:
                out |= self._types(doc, v)
            return out
        t = s.get("type")
        if isinstance(t, list):
            return set(t)
        if isinstance(t, str):
            return {t}
        if "properties" in s:
            return {"object"}
        if "enum" in s or "const" in s:
            return {type(x).__name__ for x in s.get("enum", [s.get("const")])}
        return {"any"}

    def _enum(self, doc: Doc, schema: Schema) -> list[Any] | None:
        s = self._resolve(doc, schema)
        variants = s.get("anyOf") or s.get("oneOf")
        if variants:
            values: list[Any] = []
            for v in variants:
                e = self._enum(doc, v)
                if e is None:
                    if self._types(doc, v) != {"null"}:
                        return None
                    e = [None]
                values += e
            return values
        if "enum" in s:
            return list(s["enum"])
        if "const" in s:
            return [s["const"]]
        return None

    def _object_parts(self, doc: Doc, schema: Schema) -> tuple[dict[str, Schema], set[str], Any]:
        s = self._resolve(doc, schema)
        variants = [self._resolve(doc, v) for v in (s.get("anyOf") or s.get("oneOf") or [])]
        objs = [v for v in variants if "properties" in v] or [s]
        if len(objs) != 1:
            return {}, set(), True
        o = objs[0]
        return (
            dict(o.get("properties", {})),
            set(o.get("required", [])),
            o.get("additionalProperties", True),
        )

    def _items(self, doc: Doc, schema: Schema) -> Schema | None:
        s = self._resolve(doc, schema)
        for v in [s, *(self._resolve(doc, x) for x in (s.get("anyOf") or s.get("oneOf") or []))]:
            if "items" in v:
                items: Schema = v["items"]
                return items
        return None

    def _key(self, schema: Schema) -> str:
        return json.dumps(schema, sort_keys=True)

    # -- schemas ---------------------------------------------------------------------------
    def schema(self, old_s: Schema, new_s: Schema, loc: str, direction: str) -> None:
        key = (self._key(old_s), self._key(new_s), direction)
        if key in self._seen:
            return
        self._seen.add(key)
        o, n = self._resolve(self.old, old_s), self._resolve(self.new, new_s)
        ot, nt = self._types(self.old, old_s), self._types(self.new, new_s)
        if direction == "request":
            if "any" not in nt and not ot <= nt:
                self._flag(loc, f"request type narrowed {sorted(ot)} -> {sorted(nt)}")
        elif "any" not in ot and not nt <= ot:
            self._flag(loc, f"response type widened {sorted(ot)} -> {sorted(nt)}")

        oe, ne = self._enum(self.old, old_s), self._enum(self.new, new_s)
        if (
            direction == "request"
            and ne is not None
            and (oe is None or not set(map(repr, oe)) <= set(map(repr, ne)))
        ):
            self._flag(loc, "request enum narrowed (value removed or enum added)")
        if (
            direction == "response"
            and oe is not None
            and (ne is None or not set(map(repr, ne)) <= set(map(repr, oe)))
        ):
            self._flag(loc, "response enum widened (value added or enum removed)")

        if o.get("format") != n.get("format") and (direction == "response" or n.get("format")):
            self._flag(loc, f"format changed {o.get('format')!r} -> {n.get('format')!r}")
        if direction == "request":
            for k in UPPER_BOUNDS:
                if k in n and (k not in o or n[k] < o[k]):
                    self._flag(loc, f"{k} lowered or added ({o.get(k)!r} -> {n[k]!r})")
            for k in LOWER_BOUNDS:
                if k in n and (k not in o or n[k] > o[k]):
                    self._flag(loc, f"{k} raised or added ({o.get(k)!r} -> {n[k]!r})")
            if n.get("pattern") is not None and n.get("pattern") != o.get("pattern"):
                self._flag(loc, "pattern added or changed")

        op, oreq, oadd = self._object_parts(self.old, old_s)
        np_, nreq, nadd = self._object_parts(self.new, new_s)
        if op or np_:
            if direction == "request":
                for name in sorted(nreq - oreq):
                    self._flag(f"{loc}.{name}", "new required request field")
                if nadd is False and oadd is not False:
                    self._flag(loc, "extra request fields newly forbidden")
                if nadd is False:
                    for name in sorted(set(op) - set(np_)):
                        self._flag(
                            f"{loc}.{name}", "request field removed (extra fields forbidden)"
                        )
            else:
                for name in sorted(set(op) - set(np_)):
                    self._flag(f"{loc}.{name}", "response field removed")
                for name in sorted(oreq - nreq):
                    if name in np_:
                        self._flag(f"{loc}.{name}", "response field no longer required")
            for name in sorted(set(op) & set(np_)):
                self.schema(op[name], np_[name], f"{loc}.{name}", direction)

        oi, ni = self._items(self.old, old_s), self._items(self.new, new_s)
        if oi is not None and ni is not None:
            self.schema(oi, ni, f"{loc}[]", direction)

    # -- operations ------------------------------------------------------------------------
    def _content(
        self, old_c: dict[str, Any], new_c: dict[str, Any], loc: str, direction: str
    ) -> None:
        for media in sorted(old_c):
            if media not in new_c:
                self._flag(loc, f"media type {media} removed")
                continue
            self.schema(
                old_c[media].get("schema", {}), new_c[media].get("schema", {}),
                f"{loc} {media}", direction,
            )  # fmt: skip

    def _params(
        self, doc: Doc, op: dict[str, Any], path_item: dict[str, Any]
    ) -> dict[tuple[str, str], Any]:
        out = {}
        for p in [*path_item.get("parameters", []), *op.get("parameters", [])]:
            p = self._resolve(doc, p)
            out[(p["in"], p["name"])] = p
        return out

    def operation(self, path: str, method: str) -> None:
        loc = f"{method.upper()} {path}"
        opi, npi = self.old["paths"][path], self.new["paths"][path]
        o, n = opi[method], npi[method]
        op_, np_ = self._params(self.old, o, opi), self._params(self.new, n, npi)
        for key in sorted(set(op_) - set(np_)):
            self._flag(f"{loc} {key[0]} param {key[1]}", "parameter removed")
        for key in sorted(np_):
            if np_[key].get("required") and not (key in op_ and op_[key].get("required")):
                self._flag(f"{loc} {key[0]} param {key[1]}", "parameter is new or newly required")
            if key in op_:
                self.schema(
                    op_[key].get("schema", {}), np_[key].get("schema", {}),
                    f"{loc} {key[0]} param {key[1]}", "request",
                )  # fmt: skip
        ob = self._resolve(self.old, o.get("requestBody")) if "requestBody" in o else None
        nb = self._resolve(self.new, n.get("requestBody")) if "requestBody" in n else None
        if nb is not None and nb.get("required") and not (ob and ob.get("required")):
            self._flag(f"{loc} body", "request body is new or newly required")
        if ob is not None and nb is not None:
            self._content(ob.get("content", {}), nb.get("content", {}), f"{loc} body", "request")
        for status in sorted(o.get("responses", {})):
            if status not in n.get("responses", {}):
                self._flag(f"{loc} response {status}", "response status removed")
                continue
            orr = self._resolve(self.old, o["responses"][status])
            nrr = self._resolve(self.new, n["responses"][status])
            self._content(
                orr.get("content", {}),
                nrr.get("content", {}),
                f"{loc} response {status}",
                "response",
            )

    def run(self) -> list[Finding]:
        for path in sorted(self.old.get("paths", {})):
            if path not in self.new.get("paths", {}):
                self._flag(path, "path removed")
                continue
            for method in METHODS:
                if method in self.old["paths"][path]:
                    if method not in self.new["paths"][path]:
                        self._flag(f"{method.upper()} {path}", "operation removed")
                    else:
                        self.operation(path, method)
        return self.findings


def breaking_changes(old: Doc, new: Doc) -> list[Finding]:
    return Checker(old, new).run()


def _git_show(ref: str, path: Path) -> str | None:
    """File content at ``ref``; None if the file does not exist there. Raises on a bad ref."""
    if subprocess.run(  # noqa: S603 — fixed argv
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],  # noqa: S607
        capture_output=True, check=False,
    ).returncode != 0:  # fmt: skip
        raise ValueError(f"unknown git ref: {ref}")
    proc = subprocess.run(  # noqa: S603 — fixed argv
        ["git", "show", f"{ref}:{path.as_posix()}"],  # noqa: S607
        capture_output=True, text=True, encoding="utf-8", check=False,
    )  # fmt: skip
    return proc.stdout if proc.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--base-ref", help="compare NEW with its own path at this git ref")
    args = parser.parse_args(argv)
    try:
        if args.base_ref:
            new_path = args.files[0] if args.files else Path("packages/contracts/openapi.json")
            old_text = _git_show(args.base_ref, new_path)
            if old_text is None:
                print(f"{new_path} does not exist at {args.base_ref}: nothing to break")
                return 0
            old_label = f"{args.base_ref}:{new_path.as_posix()}"
        elif len(args.files) == 2:
            old_text, new_path = args.files[0].read_text(encoding="utf-8"), args.files[1]
            old_label = str(args.files[0])
        else:
            parser.error("give OLD NEW, or --base-ref REF [NEW]")
        findings = breaking_changes(
            json.loads(old_text), json.loads(new_path.read_text(encoding="utf-8"))
        )
    except ValueError as exc:
        print(f"oacompat: {exc}", file=sys.stderr)
        return 2
    if findings:
        for f in findings:
            print(f)
        print(
            f"{len(findings)} breaking change(s) against {old_label}. Within /api/v1 only additive "
            "changes are allowed (IF-01); a breaking change needs /api/v2.",
            file=sys.stderr,
        )
        return 1
    print(f"no breaking changes against {old_label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
