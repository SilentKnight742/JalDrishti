"""FastAPI application factory."""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from jaldrishti_api.config import Settings, get_settings
from jaldrishti_api.db.session import close_resources
from jaldrishti_api.logging import (
    bind_request_id,
    configure_logging,
    reset_request_id,
)
from jaldrishti_api.routers.accessibility import router as accessibility_router
from jaldrishti_api.routers.events import router as events_router
from jaldrishti_api.routers.geography import router as geography_router
from jaldrishti_api.routers.hydrology import router as hydrology_router
from jaldrishti_api.routers.impact import router as impact_router
from jaldrishti_api.routers.incidents import router as incidents_router
from jaldrishti_api.routers.satellite import router as satellite_router
from jaldrishti_api.routers.status import router as status_router
from jaldrishti_api.routers.weather import router as weather_router

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(level=resolved_settings.log_level, service=resolved_settings.service_id)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        logger.info("api started", extra={"environment": resolved_settings.environment})
        yield
        await close_resources(application)
        logger.info("api stopped")

    application = FastAPI(
        title=resolved_settings.service_name,
        version=resolved_settings.version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{resolved_settings.api_prefix}/openapi.json",
    )
    application.state.settings = resolved_settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def request_logging(request: Request, call_next: object) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        token = bind_request_id(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)  # type: ignore[operator]
        except Exception:
            logger.exception(
                "request failed",
                extra={"method": request.method, "path": request.url.path},
            )
            raise
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            reset_request_id(token)
        response.headers["x-request-id"] = request_id
        logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": elapsed_ms,
                "request_id": request_id,
            },
        )
        return response

    application.include_router(status_router, prefix=resolved_settings.api_prefix)
    application.include_router(geography_router, prefix=resolved_settings.api_prefix)
    application.include_router(hydrology_router, prefix=resolved_settings.api_prefix)
    application.include_router(weather_router, prefix=resolved_settings.api_prefix)
    application.include_router(events_router, prefix=resolved_settings.api_prefix)
    application.include_router(satellite_router, prefix=resolved_settings.api_prefix)
    application.include_router(impact_router, prefix=resolved_settings.api_prefix)
    application.include_router(accessibility_router, prefix=resolved_settings.api_prefix)
    application.include_router(incidents_router, prefix=resolved_settings.api_prefix)
    return application


app = create_app()
