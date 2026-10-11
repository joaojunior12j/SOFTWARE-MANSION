"""Transactional persistence for CEP correlations and event links."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backend.core.correlation_engine import CorrelationResult


INSERT_CORRELATION_SQL = text(
    """
    INSERT INTO correlations (
        correlation_id,
        rule_triggered,
        confidence_score,
        event_ids,
        created_at
    ) VALUES (
        :correlation_id,
        :rule_triggered,
        :confidence_score,
        CAST(:event_ids AS UUID[]),
        :created_at
    )
    ON CONFLICT (correlation_id) DO NOTHING
    """
)

LINK_EVENTS_SQL = text(
    """
    UPDATE events
    SET correlation_id = :correlation_id
    WHERE event_id = ANY(CAST(:event_ids AS UUID[]))
    """
)

INSERT_ALARM_SQL = text(
    """
    INSERT INTO alarms (
        correlation_id,
        title,
        description,
        priority_level,
        state,
        zone_partition,
        triggered_at
    )
    SELECT
        :correlation_id,
        :title,
        :description,
        :priority_level,
        'UNACKNOWLEDGED',
        :zone_partition,
        :triggered_at
    WHERE NOT EXISTS (
        SELECT 1 FROM alarms WHERE correlation_id = :correlation_id
    )
    """
)


class CorrelationRepository:
    """Persist a correlation and link every source event atomically."""

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
        self._owns_engine = engine is None

    async def save(self, result: CorrelationResult) -> None:
        """Insert one correlation and set its UUID on all source events."""
        parameters = {
            "correlation_id": str(result.correlation_id),
            "rule_triggered": result.rule_triggered,
            "confidence_score": result.confidence_score,
            "event_ids": [str(event_id) for event_id in result.event_ids],
            "title": result.title,
            "description": result.description,
            "priority_level": result.priority_level,
            "zone_partition": result.zone_partition,
            "triggered_at": result.triggered_at,
            "created_at": result.created_at,
        }
        async with self.engine.begin() as connection:
            await connection.execute(INSERT_CORRELATION_SQL, parameters)
            await connection.execute(LINK_EVENTS_SQL, parameters)
            await connection.execute(INSERT_ALARM_SQL, parameters)

    async def close(self) -> None:
        """Dispose only an engine created by this repository."""
        if self._owns_engine:
            await self.engine.dispose()
