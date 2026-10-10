"""Queries for alarms displayed by the supervisory API."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backend.api.schemas import AlarmRead


LIST_ACTIVE_ALARMS_SQL = text(
    """
    SELECT
        alarm_id,
        correlation_id,
        title,
        description,
        priority_level,
        state,
        zone_partition,
        triggered_at,
        acknowledged_at,
        acknowledged_by,
        cleared_at
    FROM alarms
    WHERE state <> 'CLEARED'
    ORDER BY
        CASE priority_level
            WHEN 'CRITICAL' THEN 1
            WHEN 'HIGH' THEN 2
            WHEN 'MEDIUM' THEN 3
            WHEN 'LOW' THEN 4
        END,
        triggered_at DESC
    """
)


class AlarmRepository:
    """Load active alarms in operator priority order."""

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

    async def list_active(self) -> list[AlarmRead]:
        """Return every alarm not yet cleared, ordered by urgency and time."""
        async with self.engine.connect() as connection:
            result = await connection.execute(LIST_ACTIVE_ALARMS_SQL)
            return [
                AlarmRead.model_validate(dict(row))
                for row in result.mappings().all()
            ]

    async def close(self) -> None:
        """Release the SQLAlchemy connection pool."""
        await self.engine.dispose()
