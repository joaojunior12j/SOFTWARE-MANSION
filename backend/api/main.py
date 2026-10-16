"""FastAPI application for the PSIM Mansion supervisory backend."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.event_stream import EventStream, MQTTEventBridge
from backend.api.routes.alarmes import router as alarm_router
from backend.api.routes.eventos import router as event_router
from backend.api.routes.status import router as status_router
from backend.api.routes.risco import router as risk_router
from backend.core.risk_calendar import RiskCalendar
from backend.core.settings import load_settings
from backend.core.topics import event_subscription_topic
from backend.db.alarm_repository import AlarmRepository


def create_app(
    settings: Mapping[str, Any] | None = None,
    alarm_repository: Any | None = None,
    event_stream: EventStream | None = None,
    start_services: bool = True,
    risk_clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    """Create an app with injectable dependencies for tests and local use."""
    resolved_settings = dict(settings or load_settings())
    stream = event_stream or EventStream()
    owns_repository = alarm_repository is None

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        repository = alarm_repository or AlarmRepository(
            resolved_settings["database"]["url"]
        )
        application.state.alarm_repository = repository
        application.state.event_stream = stream
        bridge = None
        if start_services:
            mqtt_settings = resolved_settings["mqtt"]
            bridge = MQTTEventBridge(
                host=mqtt_settings["host"],
                port=mqtt_settings["port"],
                keepalive=mqtt_settings["keepalive"],
                topic=event_subscription_topic(
                    resolved_settings["system"]["account_id"]
                ),
                stream=stream,
                loop=asyncio.get_running_loop(),
            )
            await bridge.start()
        application.state.mqtt_bridge = bridge
        try:
            yield
        finally:
            if bridge is not None:
                await bridge.close()
            if owns_repository:
                await repository.close()

    application = FastAPI(
        title="PSIM Mansion API",
        version=resolved_settings["system"]["version"],
        lifespan=lifespan,
    )
    application.state.event_stream = stream
    application.state.alarm_repository = alarm_repository
    application.state.mqtt_bridge = None
    application.state.risk_calendar = RiskCalendar.from_settings(
        resolved_settings,
    )
    application.state.risk_clock = risk_clock or (
        lambda: datetime.now(timezone.utc)
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings["api"]["cors_origins"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(alarm_router)
    application.include_router(event_router)
    application.include_router(status_router)
    application.include_router(risk_router)
    return application


app = create_app()
