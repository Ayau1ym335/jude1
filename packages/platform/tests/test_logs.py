"""UT-logging: JSON log lines carry no personal data, secrets or mesh data (XC-FND-11)."""

import io
import json
import logging
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from jude_platform import correlation
from jude_platform.logs import configure_logging, redact

SCHEMA = json.loads((Path(__file__).parents[1] / "log-schema.json").read_text(encoding="utf-8"))
SEEDS = [
    "Иванова Айгерим",
    "870101300123",
    "+7 701 123 45 67",
    "aigerim@example.kz",
    "s3cr3t-T0ken",
]


@pytest.fixture
def capture() -> Any:
    buf = io.StringIO()
    configure_logging("test", distribution="jude-platform", stream=buf)

    def lines() -> list[dict[str, Any]]:
        out = [json.loads(line) for line in buf.getvalue().splitlines() if line]
        for doc in out:
            jsonschema.validate(doc, SCHEMA)
        return out

    lines.raw = buf  # type: ignore[attr-defined]
    yield lines
    logging.getLogger().handlers = []


def test_event_line_has_schema_fields(capture: Any) -> None:
    with correlation.bound("abcdef0123456789"):
        logging.getLogger("jude.test").info("http.request", extra={"method": "GET", "status": 200})
    (doc,) = capture()
    assert doc["event"] == "http.request"
    assert doc["correlation_id"] == "abcdef0123456789"
    assert doc["ts"].endswith("Z")
    assert (doc["method"], doc["status"]) == ("GET", 200)


def test_message_args_are_never_interpolated(capture: Any) -> None:
    log = logging.getLogger("jude.test")
    log.info("case.created %s", SEEDS[0])
    log.warning("Patient %s phone %s", SEEDS[0], SEEDS[2])
    docs = capture()
    assert [d["event"] for d in docs] == ["log.unstructured", "log.unstructured"]
    assert SEEDS[0] not in capture.raw.getvalue()


def test_unknown_or_mistyped_fields_are_dropped(capture: Any) -> None:
    logging.getLogger("jude.test").info(
        "http.request",
        extra={"clinic_ref": SEEDS[0], "body": {"x": 1}, "status": "200", "query": "q=" + SEEDS[0]},
    )
    (doc,) = capture()
    assert doc["dropped_fields"] == 4
    assert "status" not in doc
    assert SEEDS[0] not in capture.raw.getvalue()


def test_exception_logged_as_type_and_frames_only(capture: Any) -> None:
    try:
        raise ValueError(f"cannot parse {SEEDS[0]} {SEEDS[1]}")
    except ValueError:
        logging.getLogger("jude.test").exception("http.unhandled_exception")
    (doc,) = capture()
    assert doc["exc_type"] == "builtins.ValueError"
    assert doc["frames"] and all(f.count(":") == 2 for f in doc["frames"])
    raw = capture.raw.getvalue()
    assert all(seed not in raw for seed in SEEDS)


def test_trusted_text_is_redacted(capture: Any) -> None:
    logging.getLogger("uvicorn.error").info("client %s sent token=%s", SEEDS[3], SEEDS[4])
    (doc,) = capture()
    assert doc["event"] == "log.text"
    assert SEEDS[3] not in doc["text"] and SEEDS[4] not in doc["text"]


@pytest.mark.parametrize(
    "text",
    [
        "mail aigerim@example.kz here",
        "iin 870101300123 here",
        "call +7 701 123 45 67",
        "Authorization: Bearer abc.def.ghi",
        "password=hunter2",
        "session: 9f8e7d",
    ],
)
def test_redaction_net(text: str) -> None:
    assert "[redacted]" in redact(text)


def test_redaction_keeps_ids_and_timestamps() -> None:
    line = '{"correlation_id":"0123456789abcdef0123456789abcdef","ts":"2026-11-19T10:00:00.000Z"}'
    assert redact(line) == line


def test_uvicorn_access_log_disabled(capture: Any) -> None:
    logging.getLogger("uvicorn.access").info(
        '127.0.0.1 - "GET /api/v1/cases?q=%s HTTP/1.1" 200', SEEDS[0]
    )
    assert capture() == []
