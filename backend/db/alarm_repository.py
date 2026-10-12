"""Queries for alarms displayed by the supervisory API."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backend.api.schemas import AlarmRead


LIST_ACTIVE_ALARMS_SQL = text(
    """
    SELECT
        alarms.alarm_id,
        alarms.correlation_id,
        alarms.title,
        alarms.description,
        alarms.priority_level,
        alarms.state,
        alarms.zone_partition,
        alarms.triggered_at,
        alarms.acknowledged_at,
        alarms.acknowledged_by,
        alarms.cleared_at,
        correlations.rule_triggered,
        COALESCE(
            ARRAY(
                SELECT DISTINCT event.sia_code
                FROM events AS event
                WHERE event.correlation_id = alarms.correlation_id
                ORDER BY event.sia_code
            ),
            ARRAY[]::VARCHAR[]
        ) AS sia_codes
    FROM alarms
    LEFT JOIN correlations
        ON correlations.correlation_id = alarms.correlation_id
    WHERE alarms.state <> 'CLEARED'
    ORDER BY
        CASE alarms.priority_level
            WHEN 'CRITICAL' THEN 1
            WHEN 'HIGH' THEN 2
            WHEN 'MEDIUM' THEN 3
            WHEN 'LOW' THEN 4
        END,
        alarms.triggered_at DESC
    """
)

LOCK_ALARM_SQL = text(
    """
    SELECT state
    FROM alarms
    WHERE alarm_id = :alarm_id
    FOR UPDATE
    """
)

ACKNOWLEDGE_ALARM_SQL = text(
    """
    UPDATE alarms
    SET
        state = 'ACKNOWLEDGED',
        acknowledged_at = NOW(),
        acknowledged_by = :acknowledged_by
    WHERE alarm_id = :alarm_id
    RETURNING
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
        cleared_at,
        (
            SELECT rule_triggered
            FROM correlations
            WHERE correlation_id = alarms.correlation_id
        ) AS rule_triggered,
        COALESCE(
            ARRAY(
                SELECT DISTINCT event.sia_code
                FROM events AS event
                WHERE event.correlation_id = alarms.correlation_id
                ORDER BY event.sia_code
            ),
            ARRAY[]::VARCHAR[]
        ) AS sia_codes
    """
)


class AlarmNotFoundError(LookupError):
    """Raised when an alarm identifier does not exist."""


class InvalidAlarmTransitionError(ValueError):
    """Raised when an ISA-18.2 state transition is not allowed."""


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

    async def acknowledge(
        self,
        alarm_id: UUID,
        acknowledged_by: UUID,
    ) -> AlarmRead:
        """Atomically transition an unacknowledged alarm to acknowledged."""
        parameters = {
            "alarm_id": str(alarm_id),
            "acknowledged_by": str(acknowledged_by),
        }
        async with self.engine.begin() as connection:
            locked = await connection.execute(LOCK_ALARM_SQL, parameters)
            state = locked.scalar_one_or_none()
            if state is None:
                raise AlarmNotFoundError(str(alarm_id))
            if state != "UNACKNOWLEDGED":
                raise InvalidAlarmTransitionError(
                    f"cannot acknowledge alarm in state {state}"
                )
            updated = await connection.execute(
                ACKNOWLEDGE_ALARM_SQL,
                parameters,
            )
            return AlarmRead.model_validate(dict(updated.mappings().one()))

    async def close(self) -> None:
        """Release the SQLAlchemy connection pool."""
        await self.engine.dispose()
