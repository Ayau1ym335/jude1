"""Request context middleware (XC-FND-11): correlation ID, request log line, metrics, 500s.

Pure ASGI (no BaseHTTPMiddleware), so the correlation context covers the whole request,
including the handling of unhandled exceptions, which become DS-24 500 INTERNAL here.
The request log line carries the route *template* (``/api/v1/cases/{case_id}``), never the
raw path or query string, and no headers or bodies.
"""

from collections import defaultdict
import logging
import threading
import time
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from jude_api.platform.errors import error_response
from jude_platform import correlation

log = logging.getLogger("jude_api.request")
UNMATCHED = "unmatched"
# Probes: counted in metrics, not logged (compose polls them every few seconds).
QUIET_ROUTES = frozenset({"/livez", "/readyz", "/metrics", "/api/v1/health"})


class Metrics:
    """Minimal in-process counters rendered in Prometheus text format (basic metrics)."""

    def __init__(self, service: str, version: str) -> None:
        self.service, self.version = service, version
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._dur_sum: dict[str, float] = defaultdict(float)
        self._dur_count: dict[str, int] = defaultdict(int)

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self._requests[(method, route, status)] += 1
            self._dur_sum[route] += seconds
            self._dur_count[route] += 1

    def render(self) -> str:
        req = "jude_http_requests_total"
        dur = "jude_http_request_duration_seconds"
        with self._lock:
            lines = [
                "# HELP jude_build_info Build version of the running service.",
                "# TYPE jude_build_info gauge",
                f'jude_build_info{{service="{self.service}",version="{self.version}"}} 1',
                f"# HELP {req} HTTP requests by method, route template and status.",
                f"# TYPE {req} counter",
            ]
            for (method, route, status), n in sorted(self._requests.items()):
                labels = f'method="{method}",route="{route}",status="{status}"'
                lines.append(f"{req}{{{labels}}} {n}")
            lines += [
                f"# HELP {dur} Request duration by route template.",
                f"# TYPE {dur} summary",
            ]
            for route in sorted(self._dur_count):
                lines.append(f'{dur}_sum{{route="{route}"}} {self._dur_sum[route]:.6f}')
                lines.append(f'{dur}_count{{route="{route}"}} {self._dur_count[route]}')
        return "\n".join(lines) + "\n"


def _incoming_id(scope: Scope) -> str | None:
    wanted = correlation.HEADER.lower().encode("latin-1")
    for name, value in scope.get("headers", []):
        if name == wanted:
            return str(value.decode("latin-1"))
    return None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, metrics: Metrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cid = correlation.accept(_incoming_id(scope))
        state: dict[str, Any] = {"status": 500, "started": False}

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                state["status"], state["started"] = message["status"], True
                MutableHeaders(scope=message).append(correlation.HEADER, cid)
            await send(message)

        start = time.perf_counter()
        with correlation.bound(cid):
            try:
                await self.app(scope, receive, send_with_id)
            except Exception:
                log.exception("http.unhandled_exception", extra={"error_code": "INTERNAL"})
                if not state["started"]:
                    await error_response("INTERNAL")(scope, receive, send_with_id)
                state["status"] = 500
            finally:
                route_obj = scope.get("route")
                route = str(getattr(route_obj, "path", UNMATCHED))
                seconds = time.perf_counter() - start
                method = str(scope.get("method", ""))
                self.metrics.observe(method, route, int(state["status"]), seconds)
                if route not in QUIET_ROUTES:
                    log.info(
                        "http.request",
                        extra={
                            "method": method,
                            "route": route,
                            "status": int(state["status"]),
                            "duration_ms": seconds * 1000.0,
                        },
                    )
