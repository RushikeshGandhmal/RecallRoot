from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sqlalchemy.exc import SQLAlchemyError

from recallgraph.config import Settings, get_settings
from recallgraph.database import Database
from recallgraph.routes import agent, demo, health, incidents, integrations, memories
from recallgraph.telemetry.metrics import configure_telemetry


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    database = Database(app_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        telemetry = configure_telemetry(app_settings)
        database.create_schema()
        try:
            yield
        finally:
            telemetry.shutdown()
            database.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        description=(
            "Cross-session causal debugger for stateful AI agents: observe, trace, "
            "quarantine, replay, and verify."
        ),
        debug=app_settings.debug,
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.database = database
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    application.include_router(health.router)
    application.include_router(demo.router)
    application.include_router(agent.router)
    application.include_router(incidents.router)
    application.include_router(memories.router)
    application.include_router(integrations.router)

    @application.exception_handler(SQLAlchemyError)
    async def database_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": {
                    "code": "database_unavailable",
                    "message": "The operational database could not complete the request.",
                }
            },
        )

    FastAPIInstrumentor.instrument_app(application)
    return application


app = create_app()
