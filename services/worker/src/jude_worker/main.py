"""Worker process entry point: kernel warm-up, health endpoint, job loop (FN-JOB-02)."""

from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import signal
import socket
import threading
import uuid

import psycopg

import jude_kernel
from jude_platform.logs import configure_logging
from jude_worker.jobs.executor import ForkExecutor, Limits
from jude_worker.jobs.handlers import HANDLERS
from jude_worker.jobs.loop import Worker
from jude_worker.jobs.queue import LEASE_SECONDS
from jude_worker.kernel_warmup import warm_up

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
    limits = Limits.from_env()  # fail fast: no default limits (SEC-07)
    warm_up()  # every numba kernel loaded before /healthz answers (X-06 §6.4)
    port = int(os.environ.get("JUDE_WORKER_HEALTH_PORT", "8001"))
    server = make_health_server("0.0.0.0", port, postgres_check)  # noqa: S104 — container-internal port
    stop = threading.Event()

    def _shutdown(signum: int, frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    jobs = threading.Thread(target=run_jobs, args=(stop, worker_id, limits), daemon=True)
    jobs.start()
    log.info("worker.started", extra={"port": port, "component": f"{len(HANDLERS)} job types"})
    stop.wait()
    server.shutdown()


def run_jobs(stop: threading.Event, worker_id: str, limits: Limits) -> None:
    """Job loop thread; on a crash the process stops so the container restarts it."""
    url = os.environ["JUDE_DATABASE_URL"]
    try:
        with psycopg.connect(url) as conn, psycopg.connect(url, autocommit=True) as listen:
            executor = ForkExecutor(limits, LEASE_SECONDS)
            Worker(conn, worker_id, HANDLERS, executor).run_forever(stop, listen)
    except Exception:
        log.exception("worker.loop_crashed")
        stop.set()


if __name__ == "__main__":
    main()
