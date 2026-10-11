"""Day 8 smoke test for real TimescaleDB correlation persistence."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import text

from backend.api.schemas import AlarmEvent
from backend.core.correlation_engine import CorrelationEngine
from backend.core.settings import load_settings
from backend.db.correlation_repository import CorrelationRepository
from backend.db.repository import EventRepository


class SmokeRule:
    """Match two smoke events to exercise the Day 8 persistence path."""

    rule_id = "SMOKE_DAY8"
    confidence_score = 1.0

    def match(self, events):
        return events if len(events) == 2 else None


def build_event(event_id, timestamp, hardware_id) -> AlarmEvent:
    """Build one isolated smoke event with the canonical payload."""
    return AlarmEvent(
        event_id=event_id,
        timestamp=timestamp,
        account_id="SMOKE8",
        source_type="PERIMETER_SENSOR",
        device_hardware_id=hardware_id,
        zone_partition="D8",
        zone_number=8,
        sia_code="BA",
        event_status="ACTIVE",
        priority_level="CRITICAL",
        correlation_id=None,
    )


async def run() -> None:
    """Persist, correlate, verify, and remove isolated smoke records."""
    settings = load_settings()
    event_repository = EventRepository(settings["database"]["url"])
    correlation_repository = CorrelationRepository(
        engine=event_repository.engine
    )
    correlation_id = uuid4()
    engine = CorrelationEngine(
        60,
        rules=[SmokeRule()],
        uuid_factory=lambda: correlation_id,
    )
    started_at = datetime.now(timezone.utc)
    events = (
        build_event(uuid4(), started_at, "SMOKE-D8-1"),
        build_event(uuid4(), started_at + timedelta(seconds=1), "SMOKE-D8-2"),
    )
    event_ids = [str(event.event_id) for event in events]
    persisted_event_ids = []

    try:
        for event in events:
            await event_repository.save(
                event,
                event.model_dump(mode="json"),
            )
            persisted_event_ids.append(str(event.event_id))
        self_result = engine.process(events[0])
        if self_result:
            raise RuntimeError("correlation fired before both events arrived")
        results = engine.process(events[1])
        if len(results) != 1:
            raise RuntimeError("expected one Day 8 smoke correlation")
        await correlation_repository.save(results[0])

        async with event_repository.engine.connect() as connection:
            linked = await connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM events
                    WHERE correlation_id = :correlation_id
                      AND event_id = ANY(CAST(:event_ids AS UUID[]))
                    """
                ),
                {
                    "correlation_id": str(correlation_id),
                    "event_ids": event_ids,
                },
            )
            if linked.scalar_one() != 2:
                raise RuntimeError("source events were not linked")
    finally:
        if persisted_event_ids:
            async with event_repository.engine.begin() as connection:
                await connection.execute(
                    text(
                        "DELETE FROM events "
                        "WHERE event_id = ANY(CAST(:event_ids AS UUID[]))"
                    ),
                    {"event_ids": persisted_event_ids},
                )
                await connection.execute(
                    text(
                        "DELETE FROM correlations "
                        "WHERE correlation_id = :correlation_id"
                    ),
                    {"correlation_id": str(correlation_id)},
                )
        await event_repository.close()

    print("day8_correlation=1 linked_events=2 database=ok")


def main() -> None:
    """Run the asynchronous database smoke test."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
