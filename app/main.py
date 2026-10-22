"""ForgeGuard Orchestration Backend — Main Application Entrypoint."""
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.cost_analysis import router as cost_analysis_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.machines import router as machines_router
from app.api.preemption import router as preemption_router
from app.api.schedule import router as schedule_router
from app.api.simulation import router as simulation_router
from app.api.status import router as status_router
from app.api.technicians import router as technicians_router
from app.config import get_settings
from app.schemas.common import ApiErrorDetail, ErrorResponse

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("forgeguard.orchestration")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    settings = get_settings()
    logger.info(
        f"Starting ForgeGuard Orchestration Backend on {settings.orchestration_host}:{settings.orchestration_port} (Env: {settings.environment})"
    )
    logger.info(f"Configured Engine Base URL: {settings.engine_base_url}")
    yield
    logger.info("Shutting down ForgeGuard Orchestration Backend")


def create_app() -> FastAPI:
    """Builds and configures the FastAPI application instance."""
    settings = get_settings()

    app = FastAPI(
        title="ForgeGuard Orchestration Backend",
        description=(
            "Central orchestration service coordinating ML predictions, Decision Engine operations, "
            "shift scheduling, equipment safety gates, guarded preemption, and real-time state for the "
            "ForgeGuard predictive maintenance command center."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # 1. CORS Configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Consistent Error Handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        req_id = request.headers.get("X-Request-ID", f"req-{uuid.uuid4().hex[:8]}")
        code_map = {
            400: "BAD_REQUEST",
            404: "RESOURCE_NOT_FOUND",
            409: "STATE_CONFLICT",
            422: "VALIDATION_ERROR",
            502: "UPSTREAM_GATEWAY_ERROR",
            503: "SERVICE_UNAVAILABLE",
        }
        code = code_map.get(exc.status_code, "HTTP_ERROR")
        error_body = ErrorResponse(
            error=ApiErrorDetail(
                code=code,
                message=str(exc.detail),
                details=None,
            ),
            request_id=req_id,
        )
        return JSONResponse(status_code=exc.status_code, content=error_body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        req_id = request.headers.get("X-Request-ID", f"req-{uuid.uuid4().hex[:8]}")
        error_body = ErrorResponse(
            error=ApiErrorDetail(
                code="VALIDATION_ERROR",
                message="Invalid request body or parameters",
                details=exc.errors(),
            ),
            request_id=req_id,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_body.model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        req_id = request.headers.get("X-Request-ID", f"req-{uuid.uuid4().hex[:8]}")
        logger.error(f"Unhandled exception during request {request.method} {request.url.path} [{req_id}]: {exc}", exc_info=True)
        # Never leak raw stack traces to UI
        error_body = ErrorResponse(
            error=ApiErrorDetail(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected internal error occurred. Please contact system support.",
                details=None,
            ),
            request_id=req_id,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body.model_dump(),
        )

    # 3. Register All Route Handlers
    app.include_router(health_router)
    app.include_router(status_router)
    app.include_router(simulation_router)
    app.include_router(machines_router)
    app.include_router(jobs_router)
    app.include_router(technicians_router)
    app.include_router(schedule_router)
    app.include_router(preemption_router)
    app.include_router(events_router)
    app.include_router(cost_analysis_router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.orchestration_host,
        port=settings.orchestration_port,
        reload=True,
    )
