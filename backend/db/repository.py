"""Persistence of canonical MQTT events in TimescaleDB."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backend.api.schemas import AlarmEvent


INSERT_EVENT_SQL = text(
    """
    INSERT INTO events (
        event_id,
        timestamp,
        account_id,
        source_type,
        device_hardware_id,
        zone_partition,
        zone_number,
        sia_code,
        event_status,
        priority_level,
        correlation_id,
        raw_payload
    ) VALUES (
        :event_id,
        :timestamp,
        :account_id,
        :source_type,
        :device_hardware_id,
        :zone_partition,
        :zone_number,
        :sia_code,
        :event_status,
        :priority_level,
        :correlation_id,
        CAST(:raw_payload AS JSONB)
    )
    ON CONFLICT (event_id, timestamp) DO NOTHING
    """
)


class EventRepository:
    """Store normalized events while preserving their original JSON payload."""

    def __init__(
        self,
        database_url: str | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required")
        self.engine = engine or create_async_engine(
            database_url,
            pool_pre_ping=True,
        )

    async def save(
        self,
        event: AlarmEvent,
        raw_payload: dict[str, Any],
    ) -> None:
        """Insert one event idempotently using its composite hypertable key."""
        parameters = event.model_dump(mode="python")
        parameters["event_id"] = str(event.event_id)
        parameters["correlation_id"] = (
            str(event.correlation_id) if event.correlation_id else None
        )
        parameters["raw_payload"] = json.dumps(
            raw_payload,
            separators=(",", ":"),
        )
        async with self.engine.begin() as connection:
            await connection.execute(INSERT_EVENT_SQL, parameters)

    async def close(self) -> None:
        """Release the SQLAlchemy connection pool."""
        await self.engine.dispose()
