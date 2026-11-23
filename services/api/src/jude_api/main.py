"""FastAPI application factory.

/api/v1 holds the public API (IDR-05); /livez, /readyz and /metrics are internal probes
(XC-FND-11). Every request runs inside RequestContextMiddleware (correlation ID, request log
line, metrics, DS-24 500s); refusals use the DS-24 envelope (jude_api.platform.errors).
"""

from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
import os
import threading
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
import psycopg

from jude_api.domain.iam.routes import router as auth_router
from jude_api.domain.iam.user_routes import router as users_router
from jude_api.platform import completion, deps
from jude_api.platform.authz import assert_every_route_authorised
from jude_api.platform.deps import requester
from jude_api.platform.errors import install_error_handlers
from jude_api.platform.iam import assert_mutations_need_a_session
from jude_api.platform.job_routes import router as jobs_router
from jude_api.platform.middleware import Metrics, RequestContextMiddleware
from jude_api.platform.probes import DEFAULT_CHECKS, Check, probe_router
from jude_api.platform.schemas import ERROR_RESPONSES, HealthResponse
from jude_platform.logs import build_version, configure_logging

API_PREFIX = "/api/v1"
# Version of the contract document (IF-01): the major version of the URI. Additive changes keep
# it; a breaking change means /api/v2. The build version is in /metrics and in every log line.
API_CONTRACT_VERSION = "1"
DB_CONNECT_TIMEOUT_S = 2
DISTRIBUTION = "jude-api"

DbCheck = Callable[[], None]


def postgres_check() -> None:
    """Raise if Postgres is not reachable. Reads JUDE_DATABASE_URL."""
    url = os.environ["JUDE_DATABASE_URL"]
    with psycopg.connect(url, connect_timeout=DB_CONNECT_TIMEOUT_S) as conn:
        conn.execute("SELECT 1")


def operation_id(route: APIRoute) -> str:
    """Stable operationId = the endpoint function name (the generated client's method names)."""
    return route.name


def create_app(
    db_check: DbCheck = postgres_check,
    readiness_checks: Mapping[str, Check] = DEFAULT_CHECKS,
) -> FastAPI:
    version = build_version(DISTRIBUTION)
    app = FastAPI(
        title="Jude API",
        version=API_CONTRACT_VERSION,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=None,
        redoc_url=None,
        generate_unique_id_function=operation_id,
    )
    metrics = Metrics("api", version)
    app.add_middleware(RequestContextMiddleware, metrics=metrics)
    install_error_handlers(app)

    router = APIRouter(prefix=API_PREFIX, responses=ERROR_RESPONSES)

    @router.get(
        "/health",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse, "description": "Database unreachable"}},
    )
    def health() -> JSONResponse:
        try:
            db_check()
        except Exception:  # any failure means "not healthy"; details stay out of the response
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "service": "api", "checks": {"database": "fail"}},
            )
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "service": "api", "checks": {"database": "ok"}},
        )

    app.include_router(router)
    app.include_router(jobs_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(probe_router(metrics, readiness_checks))
    assert_mutations_need_a_session(app, requester)  # deny by default (FN-IAM-02, SEC-20)
    assert_every_route_authorised(app)  # deny by default (FN-IAM-04)
    return app


def build() -> FastAPI:
    """Entry point for uvicorn (``--factory jude_api.main:build``): logging first, then the app,
    then the job completion handler (FN-JOB-04) as a background thread of the API process."""
    configure_logging("api", distribution=DISTRIBUTION)
    app = create_app()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        stop = threading.Event()
        thread = threading.Thread(
            target=completion.run_supervised,
            args=(_app_connection, completion.HANDLERS, deps.utc_now, stop),
            daemon=True,
            name="job-completion",
        )
        thread.start()
        yield
        stop.set()
        thread.join(5)

    app.router.lifespan_context = lifespan
    return app


def _app_connection() -> psycopg.Connection[Any]:
    conn = psycopg.connect(os.environ["JUDE_DATABASE_URL"], connect_timeout=DB_CONNECT_TIMEOUT_S)
    conn.execute(f"SET ROLE {deps.APP_ROLE}")
    conn.commit()
    return conn
