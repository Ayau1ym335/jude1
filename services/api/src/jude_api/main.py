"""FastAPI application factory.

XC-FND-02 scope: only the health endpoint under the /api/v1 prefix (IDR-05).
Readiness, structured logging and correlation IDs arrive with XC-FND-11.
"""

from collections.abc import Callable
import os

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
import psycopg

API_PREFIX = "/api/v1"
DB_CONNECT_TIMEOUT_S = 2

DbCheck = Callable[[], None]


def postgres_check() -> None:
    """Raise if Postgres is not reachable. Reads JUDE_DATABASE_URL."""
    url = os.environ["JUDE_DATABASE_URL"]
    with psycopg.connect(url, connect_timeout=DB_CONNECT_TIMEOUT_S) as conn:
        conn.execute("SELECT 1")


def create_app(db_check: DbCheck = postgres_check) -> FastAPI:
    app = FastAPI(
        title="Jude API",
        version="0.0.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    router = APIRouter(prefix=API_PREFIX)

    @router.get("/health")
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
    return app


app = create_app()
