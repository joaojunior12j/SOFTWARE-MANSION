"""Day 9 smoke test for R01, R02 and ISA-18.2 acknowledgement."""

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
    """Persist both scenarios, verify rules, acknowledge, and clean up."""
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
    correlation_ids = []

    try:
        async with event_repository.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO users (user_id, name, email, role)
                    VALUES (:user_id, 'Smoke Day 9', :email, 'OPERATOR')
                    """
                ),
                {
                    "user_id": str(operator_id),
                    "email": f"smoke-{operator_id}@example.invalid",
                },
            )

        scenarios = (
            ("rf_jammer", "SMOKE9RF"),
            ("wall_jump", "SMOKE9WJ"),
        )
        results_by_rule = {}
        for scenario_name, account_id in scenarios:
            simulation = simulator.run(scenario_name, account_id)
            for event in simulation.events:
                await event_repository.save(
                    event,
                    event.model_dump(mode="json"),
                )
                persisted_event_ids.append(str(event.event_id))
                for result in correlation_engine.process(event):
                    await correlation_repository.save(result)
                    correlation_ids.append(str(result.correlation_id))
                    results_by_rule[result.rule_triggered] = result

        if set(results_by_rule) != {"R01_JAMMER", "R02_MULTI_SENSOR"}:
            raise RuntimeError(f"unexpected rules: {sorted(results_by_rule)}")

        r01 = results_by_rule["R01_JAMMER"]
        async with event_repository.engine.connect() as connection:
            alarm_row = await connection.execute(
                text(
                    """
                    SELECT alarm_id, state, priority_level
                    FROM alarms
                    WHERE correlation_id = :correlation_id
                    """
                ),
                {"correlation_id": str(r01.correlation_id)},
            )
            alarm_id, state, priority = alarm_row.one()
        if state != "UNACKNOWLEDGED" or priority != "CRITICAL":
            raise RuntimeError("R01 alarm has an invalid initial state")

        acknowledged = await alarm_repository.acknowledge(
            alarm_id,
            operator_id,
        )
        if acknowledged.state != "ACKNOWLEDGED":
            raise RuntimeError("alarm acknowledgement was not persisted")
        if acknowledged.acknowledged_by != operator_id:
            raise RuntimeError("acknowledging operator was not persisted")
    finally:
        async with event_repository.engine.begin() as connection:
            if correlation_ids:
                await connection.execute(
                    text(
                        "DELETE FROM alarms WHERE correlation_id = "
                        "ANY(CAST(:ids AS UUID[]))"
                    ),
                    {"ids": correlation_ids},
                )
            if persisted_event_ids:
                await connection.execute(
                    text(
                        "DELETE FROM events WHERE event_id = "
                        "ANY(CAST(:ids AS UUID[]))"
                    ),
                    {"ids": persisted_event_ids},
                )
            if correlation_ids:
                await connection.execute(
                    text(
                        "DELETE FROM correlations WHERE correlation_id = "
                        "ANY(CAST(:ids AS UUID[]))"
                    ),
                    {"ids": correlation_ids},
                )
            await connection.execute(
                text("DELETE FROM users WHERE user_id = :user_id"),
                {"user_id": str(operator_id)},
            )
        await event_repository.close()

    print("rules=R01_JAMMER,R02_MULTI_SENSOR ack=ACKNOWLEDGED database=ok")


def main() -> None:
    """Run the asynchronous Day 9 integration smoke test."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
