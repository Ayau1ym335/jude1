"""RFC 8785 JSON Canonicalization Scheme (JCS), used by FN-KRP-03 (ALG-55; TD-19, TD-20).

``jcs_bytes(value)`` is the canonical UTF-8 form of a JSON value:

- **Objects**: members sorted by their keys as **UTF-16 code units** (RFC 8785 §3.2.3). This
  differs from Python's code-point order for keys beyond the BMP. No whitespace anywhere.
- **Numbers**: IEEE-754 doubles serialised as ECMAScript ``Number.prototype.toString``
  (RFC 8785 §3.2.2.3): shortest round-trip digits; plain notation for 1e-7 <= |x| < 1e21,
  exponent notation ``1e+21`` / ``1e-7`` otherwise; integral values without ``.0``; -0 -> ``0``.
  NaN and Infinity are not JSON and are refused. An int is a double: an int outside
  +-2^53 would change value, so it is refused instead.
- **Strings**: JSON.stringify escaping: ``\\"``, ``\\\\``, ``\\b \\f \\n \\r \\t``, other
  controls as ``\\u00xx`` (lower-case hex); everything else literal UTF-8. Lone surrogates are
  not valid Unicode and are refused.
- **Literals**: ``true``, ``false``, ``null``. Lists and tuples are arrays, in their order.

Every refusal is a ``KernelContractError`` (programming error, EH-KRN). The ALG-55 alternative,
``json.dumps(sort_keys=True)``, differs from JCS for some numbers and strings.

``parse_json`` reads JSON text strictly (I-JSON, RFC 7493): duplicate keys, NaN and Infinity
are refused, and an integer beyond +-2^53 reads as the double it denotes (that is how JCS
writes such doubles). Two texts that differ only in whitespace or member order therefore parse
to values with the same canonical form.
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal
import json
from typing import Any, Final

from jude_kernel.core.errors import KernelContractError

MAX_SAFE_INTEGER: Final = 2**53
_ESCAPES: Final = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n",
                   "\r": "\\r", "\t": "\\t"}  # fmt: skip


def es_number(x: float) -> str:
    """ECMAScript Number.prototype.toString for a finite double (RFC 8785 §3.2.2.3)."""
    if x != x or x in (float("inf"), float("-inf")):
        raise KernelContractError("JCS: NaN and Infinity are not JSON numbers")
    if x == 0:
        return "0"  # +0 and -0
    sign = "-" if x < 0 else ""
    # repr() is the shortest round-trip representation (same digits ECMAScript chooses).
    _, digit_tuple, exp = Decimal(repr(abs(x))).as_tuple()
    digits = "".join(map(str, digit_tuple)).rstrip("0")
    exp = int(exp) + (len(digit_tuple) - len(digits))  # trailing zeros moved into the exponent
    digits = digits.lstrip("0") or "0"
    k = len(digits)
    n = exp + k  # value = 0.digits * 10^n
    if k <= n <= 21:
        text = digits + "0" * (n - k)
    elif 0 < n <= 21:
        text = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        text = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        mantissa = digits if k == 1 else digits[0] + "." + digits[1:]
        text = f"{mantissa}e{'+' if e > 0 else '-'}{abs(e)}"
    return sign + text


def _string(s: str) -> str:
    out = ['"']
    for ch in s:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            raise KernelContractError("JCS: strings must be valid Unicode (lone surrogate)")
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif code < 0x20:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _utf16_key(key: str) -> bytes:
    return key.encode("utf-16-be")  # big-endian code units compare like unsigned 16-bit ints


def _serialise(value: Any, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise KernelContractError("JCS: integer outside +-2^53 is not exact as a double")
        out.append(es_number(float(value)))
    elif isinstance(value, float):
        out.append(es_number(value))
    elif isinstance(value, str):
        out.append(_string(value))
    elif isinstance(value, Mapping):
        keys = list(value)
        if not all(isinstance(k, str) for k in keys):
            raise KernelContractError("JCS: object keys must be strings")
        for k in keys:
            _string(k)  # validates the key
        out.append("{")
        for i, k in enumerate(sorted(keys, key=_utf16_key)):
            if i:
                out.append(",")
            out.append(_string(k))
            out.append(":")
            _serialise(value[k], out)
        out.append("}")
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        out.append("[")
        for i, item in enumerate(value):
            if i:
                out.append(",")
            _serialise(item, out)
        out.append("]")
    else:
        raise KernelContractError(f"JCS: {type(value).__name__} is not a JSON value")


def jcs_bytes(value: Any) -> bytes:
    """The RFC 8785 canonical form of ``value`` as UTF-8 bytes."""
    out: list[str] = []
    _serialise(value, out)
    return "".join(out).encode("utf-8")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, val in pairs:
        if key in result:
            raise KernelContractError(f"JSON: duplicate key {key!r} (I-JSON)")
        result[key] = val
    return result


def _number_int(text: str) -> int | float:
    """A JSON number is a double: integers beyond +-2^53 mean the double they round to."""
    value = int(text)
    return value if abs(value) <= MAX_SAFE_INTEGER else float(text)


def _no_constant(name: str) -> Any:
    raise KernelContractError(f"JSON: {name} is not a JSON number")


def parse_json(text: str) -> Any:
    """Strict JSON text -> value (no duplicate keys, no NaN/Infinity)."""
    try:
        return json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_constant=_no_constant,
            parse_int=_number_int,
        )
    except json.JSONDecodeError as exc:
        raise KernelContractError(f"JSON: {exc.msg}") from exc
