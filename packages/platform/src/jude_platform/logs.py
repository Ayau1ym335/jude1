"""Structured JSON logging that cannot carry personal data, secrets or mesh data (XC-FND-11).

One JSON object per line on stdout. The schema is ``log-schema.json`` next to this package
(LOG_SCHEMA.md explains it). Layers of protection, outermost last:

1. **Events, not messages.** ``log.info("http.request", extra={...})``: the event name is a
   static dotted identifier. The record's ``args`` are never interpolated, so
   ``log.info("case %s", clinic_ref)`` cannot leak ``clinic_ref``; a non-event message is
   logged as ``log.unstructured`` with its text dropped.
2. **Allow-listed fields.** Only keys in ``FIELDS`` with the declared type are written; every
   other ``extra`` key is dropped and counted in ``dropped_fields``. There is no field for
   request bodies, query strings, headers, file names, clinic references or arrays.
3. **Exceptions without messages.** An exception is logged as its type plus
   ``file:line:function`` frames; the exception message and locals are never written.
4. **Redaction net.** Every string value is scanned for e-mail addresses, IIN-like 12-digit
   numbers, phone numbers, bearer tokens and ``password=``/``token=`` pairs before the line
   is serialised (so redaction can never break the JSON).

Text from a few trusted third-party loggers (uvicorn server lifecycle, Alembic migration
steps) is kept, through the redaction net.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import re
import sys
from types import TracebackType
from typing import IO, Any

from jude_platform import correlation

SCHEMA_ID = "log/1"
EVENT_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
MAX_STR = 200
MAX_FRAMES = 20

# field -> allowed Python types. Values are metadata about the request or job, never content.
FIELDS: Mapping[str, tuple[type, ...]] = {
    "method": (str,),
    "route": (str,),  # route template, e.g. /api/v1/cases/{case_id}, never the raw path
    "status": (int,),
    "duration_ms": (int, float),
    "error_code": (str,),
    "http_status": (int,),
    "job_id": (str,),
    "job_type": (str,),
    "job_status": (str,),
    "attempts": (int,),
    "check": (str,),
    "ok": (bool,),
    "revision": (str,),
    "port": (int,),
    "component": (str,),
}
TRUSTED_TEXT_LOGGERS = ("uvicorn.error", "alembic.runtime.migration")
# Chatty libraries: INFO lines are noise (alembic plugin setup) or carry URLs with query
# strings (HTTP clients); their text would be dropped anyway, so keep only warnings.
QUIET_LOGGERS = ("alembic.runtime.plugins", "httpx", "httpx2", "httpcore", "urllib3")

_STD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}

_REDACT = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),  # e-mail
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),  # bearer token
    re.compile(
        r"(?i)\b(password|passwd|secret|token|session|cookie|authorization|csrf)\b\s*[=:]\s*\S+"
    ),
    re.compile(r"(?<![0-9A-Za-z])\d{12}(?![0-9A-Za-z])"),  # IIN-like number
    re.compile(
        r"(?<![0-9A-Za-z])\+?[78][\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?![0-9A-Za-z])"
    ),  # phone
]
REDACTED = "[redacted]"


def redact(text: str) -> str:
    for pattern in _REDACT:
        text = pattern.sub(REDACTED, text)
    return text


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value


def build_version(distribution: str) -> str:
    """NFR-08: the build version written on every line. JUDE_BUILD_VERSION wins (set by CI)."""
    env = os.environ.get("JUDE_BUILD_VERSION")
    if env:
        return env[:64]
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _frames(tb: TracebackType | None) -> list[str]:
    frames: list[str] = []
    while tb is not None:
        code = tb.tb_frame.f_code
        frames.append(f"{Path(code.co_filename).name}:{tb.tb_lineno}:{code.co_name}")
        tb = tb.tb_next
    return frames[-MAX_FRAMES:]


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return value[:MAX_STR]
    if isinstance(value, float):
        return round(value, 3)
    return value


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, version: str) -> None:
        super().__init__()
        self.service = service
        self.version = version

    def format(self, record: logging.LogRecord) -> str:
        doc: dict[str, Any] = {
            "schema": SCHEMA_ID,
            "ts": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "service": self.service,
            "version": self.version,
            "logger": record.name[:MAX_STR],
            "correlation_id": correlation.current(),
        }
        msg = record.msg
        if isinstance(msg, str) and EVENT_RE.fullmatch(msg):
            doc["event"] = msg
        elif record.name in TRUSTED_TEXT_LOGGERS:
            doc["event"] = "log.text"
            doc["text"] = record.getMessage()[:MAX_STR]
        else:
            doc["event"] = "log.unstructured"  # text deliberately dropped

        dropped = 0
        for key, value in record.__dict__.items():
            if key in _STD_ATTRS or key.startswith("_"):
                continue
            allowed = FIELDS.get(key)
            if (
                allowed is not None
                and isinstance(value, allowed)
                and not (isinstance(value, bool) and bool not in allowed)
            ):
                doc[key] = _clean(value)
            else:
                dropped += 1
        if dropped:
            doc["dropped_fields"] = dropped

        if record.exc_info and record.exc_info[0] is not None:
            exc_type, _, tb = record.exc_info
            doc["exc_type"] = f"{exc_type.__module__}.{exc_type.__qualname__}"[:MAX_STR]
            doc["frames"] = _frames(tb)

        doc = {k: _redact_value(v) for k, v in doc.items()}
        return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def configure_logging(
    service: str,
    *,
    distribution: str,
    level: int = logging.INFO,
    stream: IO[str] | None = None,
) -> logging.Handler:
    """Route every logger through one JSON handler. Idempotent; returns the handler."""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter(service, build_version(distribution)))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "alembic"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    # uvicorn's access log prints raw paths with query strings: replaced by http.request.
    logging.getLogger("uvicorn.access").disabled = True
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    return handler
