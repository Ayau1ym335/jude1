"""Liveness, readiness and metrics endpoints (XC-FND-11).

They live outside /api, so the same-origin proxy (Caddy routes only /api/* to the API) never
exposes them; orchestration and monitoring reach them inside the network.

- GET /livez   process is up (no dependencies).
- GET /readyz  database reachable, schema at the migration head, blob store reachable.
- GET /metrics Prometheus text (request counters and durations by route template).
"""

from collections.abc import Callable, Mapping
import logging
import os
import urllib.request

from alembic.script import ScriptDirectory
from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse
import psycopg

from jude_api.db.migrate import alembic_config
from jude_api.platform.middleware import Metrics

log = logging.getLogger("jude_api.probes")
CONNECT_TIMEOUT_S = 2

Check = Callable[[], None]


def check_database() -> None:
    with psycopg.connect(os.environ["JUDE_DATABASE_URL"], connect_timeout=CONNECT_TIMEOUT_S) as c:
        c.execute("SELECT 1")


def check_migrations() -> None:
    """The database schema must be at the head revision shipped with this build."""
    url = os.environ["JUDE_DATABASE_URL"]
    head = ScriptDirectory.from_config(alembic_config(url)).get_current_head()
    with psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_S) as c:
        row = c.execute("SELECT version_num FROM alembic_version").fetchone()
    if row is None or row[0] != head:
        raise RuntimeError("schema is not at the migration head")


def check_storage() -> None:
    base = os.environ["JUDE_STORAGE_URL"].rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ValueError("JUDE_STORAGE_URL must be http(s)")
    with urllib.request.urlopen(f"{base}/healthz", timeout=CONNECT_TIMEOUT_S) as resp:  # noqa: S310 — scheme checked above
        if resp.status != 200:
            raise RuntimeError("storage not healthy")


DEFAULT_CHECKS: Mapping[str, Check] = {
    "database": check_database,
    "migrations": check_migrations,
    "storage": check_storage,
}


def probe_router(metrics: Metrics, checks: Mapping[str, Check]) -> APIRouter:
    router = APIRouter(include_in_schema=False)

    @router.get("/livez")
    def livez() -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "api"})

    @router.get("/readyz")
    def readyz() -> JSONResponse:
        results: dict[str, str] = {}
        for name, check in checks.items():
            try:
                check()
                results[name] = "ok"
            except Exception:  # any failure means "not ready"; details stay out of the response
                results[name] = "fail"
                log.warning("readiness.check_failed", extra={"check": name, "ok": False})
        ready = all(v == "ok" for v in results.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ready" if ready else "not_ready",
                "service": "api",
                "checks": results,
            },
        )

    @router.get("/metrics")
    def metrics_text() -> PlainTextResponse:
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

    return router
