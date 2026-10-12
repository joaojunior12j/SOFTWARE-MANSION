"""Day 10 smoke test for the HMI alarm projection and acknowledgement."""

import asyncio
from uuid import uuid4

from sqlalchemy import text

from backend.core.correlation_engine import CorrelationEngine
from backend.core.correlation_rules import build_rules
from backend.core.settings import load_settings
from backend.db.alarm_repository import AlarmRepository
from backend.db.correlation_repository import CorrelationRepository
from backend.db.repository import EventRepository
from backend.simulator.engine import SimulationEngine
from backend.simulator.scenarios import build_scenarios


async def run() -> None:
    """Create R01, read its HMI projection, acknowledge it, and clean up."""
    settings = load_settings()
    event_repository = EventRepository(settings["database"]["url"])
    correlation_repository = CorrelationRepository(
        engine=event_repository.engine
    )
    alarm_repository = AlarmRepository(engine=event_repository.engine)
    correlation_engine = CorrelationEngine(
        settings["correlation_engine"]["window_seconds"],
        rules=build_rules(settings),
    )
    simulator = SimulationEngine(build_scenarios(settings))
    operator_id = uuid4()
    persisted_event_ids = []
    correlation_id = None

    try:
        async with event_repository.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO users (user_id, name, email, role)
                    VALUES (:user_id, 'Smoke Day 10', :email, 'OPERATOR')
                    """
                ),
                {
                    "user_id": str(operator_id),
                    "email": f"smoke-day10-{operator_id}@example.invalid",
                },
            )

        account_id = f"S10{uuid4().hex[:7]}"
        simulation = simulator.run("rf_jammer", account_id)
        result = None
        for event in simulation.events:
            await event_repository.save(event, event.model_dump(mode="json"))
            persisted_event_ids.append(str(event.event_id))
            for candidate in correlation_engine.process(event):
                await correlation_repository.save(candidate)
                result = candidate

        if result is None or result.rule_triggered != "R01_JAMMER":
            raise RuntimeError("R01 was not produced for the HMI smoke test")
        correlation_id = str(result.correlation_id)

        active = await alarm_repository.list_active()
        projected = next(
            alarm
            for alarm in active
            if str(alarm.correlation_id) == correlation_id
        )
        if projected.rule_triggered != "R01_JAMMER":
            raise RuntimeError(
                "HMI projection is missing the correlation rule"
            )
        if set(projected.sia_codes) != {"BA", "RP", "TA"}:
            raise RuntimeError(
                f"unexpected SIA projection: {projected.sia_codes}"
            )

        acknowledged = await alarm_repository.acknowledge(
            projected.alarm_id,
            operator_id,
        )
        if acknowledged.state != "ACKNOWLEDGED":
            raise RuntimeError("HMI acknowledgement was not persisted")
        if acknowledged.acknowledged_by != operator_id:
            raise RuntimeError("HMI acknowledgement lost the operator")
    finally:
        async with event_repository.engine.begin() as connection:
            if correlation_id is not None:
                await connection.execute(
                    text(
                        "DELETE FROM alarms WHERE correlation_id = "
                        "CAST(:correlation_id AS UUID)"
                    ),
                    {"correlation_id": correlation_id},
                )
            if persisted_event_ids:
                await connection.execute(
                    text(
                        "DELETE FROM events WHERE event_id = "
                        "ANY(CAST(:ids AS UUID[]))"
                    ),
                    {"ids": persisted_event_ids},
                )
            if correlation_id is not None:
                await connection.execute(
                    text(
                        "DELETE FROM correlations WHERE correlation_id = "
                        "CAST(:correlation_id AS UUID)"
                    ),
                    {"correlation_id": correlation_id},
                )
            await connection.execute(
                text("DELETE FROM users WHERE user_id = :user_id"),
                {"user_id": str(operator_id)},
            )
        await event_repository.close()

    print(
        "hmi_projection=ok sia=BA,RP,TA "
        "ack=ACKNOWLEDGED cleanup=ok"
    )


def main() -> None:
    """Run the asynchronous Day 10 integration smoke test."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
