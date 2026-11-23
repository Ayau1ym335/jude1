"""Security configuration SD-01 / SD-02 (SEC-05, SEC-06): read from security.json, not code."""

from dataclasses import dataclass
from functools import cache
import json
from pathlib import Path

PATH = Path(__file__).resolve().parent / "security.json"


@dataclass(frozen=True)
class SecurityConfig:
    max_failures: int
    window_seconds: int
    lock_seconds: int
    idle_timeout_seconds: int
    last_seen_write_interval_seconds: int

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"security config {name} must be a positive integer")


@cache
def security_config() -> SecurityConfig:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    return SecurityConfig(**doc["lockout"], **doc["session"])
