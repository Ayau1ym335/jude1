"""Worker process entry point.

XC-FND-02 scope: process lifecycle + health endpoint only. The job loop
(claim/lease/retry with SKIP LOCKED) arrives with TSK-JOB-*.
"""

from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import signal
import threading

import psycopg

import jude_kernel
from jude_platform.logs import configure_logging

log = logging.getLogger("jude_worker")

DB_CONNECT_TIMEOUT_S = 2
HEALTH_PATH = "/healthz"

DbCheck = Callable[[], None]


def postgres_check() -> None:
    """Raise if Postgres is not reachable. Reads JUDE_DATABASE_URL."""
    url = os.environ["JUDE_DATABASE_URL"]
    with psycopg.connect(url, connect_timeout=DB_CONNECT_TIMEOUT_S) as conn:
        conn.execute("SELECT 1")


def health_payload(db_check: DbCheck) -> tuple[int, dict[str, object]]:
    try:
        db_check()
    except Exception:  # any failure means "not healthy"; details stay out of the response
        return 503, {"status": "unavailable", "service": "worker", "checks": {"database": "fail"}}
    return 200, {
        "status": "ok",
        "service": "worker",
        "kernel_version": jude_kernel.KERNEL_VERSION,
        "checks": {"database": "ok"},
    }


def make_health_server(host: str, port: int, db_check: DbCheck) -> ThreadingHTTPServer:
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != HEALTH_PATH:
                self.send_error(404)
                return
            status, payload = health_payload(db_check)
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return  # access logs come with XC-FND-11 structured logging

    return ThreadingHTTPServer((host, port), HealthHandler)


def main() -> None:
    configure_logging("worker", distribution="jude-worker")
    port = int(os.environ.get("JUDE_WORKER_HEALTH_PORT", "8001"))
    server = make_health_server("0.0.0.0", port, postgres_check)  # noqa: S104 — container-internal port
    stop = threading.Event()

    def _shutdown(signum: int, frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info("worker.started", extra={"port": port, "component": "idle (no job handlers yet)"})
    stop.wait()
    server.shutdown()


if __name__ == "__main__":
    main()
