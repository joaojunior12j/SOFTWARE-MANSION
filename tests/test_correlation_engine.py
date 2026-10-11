"""Tests for the Day 8 sliding-window correlation foundation."""

from datetime import datetime, timedelta, timezone
from uuid import UUID
import unittest

from backend.api.schemas import AlarmEvent
from backend.core.correlation_engine import CorrelationEngine
from tests.test_event_contract import CANONICAL_EVENT


START = datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc)


def make_event(
    number: int,
    seconds: float,
    account_id: str = "1234",
    zone_partition: str = "01",
) -> AlarmEvent:
    """Build one deterministic canonical event for a correlation window."""
    return AlarmEvent.model_validate(
        {
            **CANONICAL_EVENT,
            "event_id": UUID(int=number),
            "timestamp": START + timedelta(seconds=seconds),
            "account_id": account_id,
            "zone_partition": zone_partition,
            "device_hardware_id": f"DEVICE-{number}",
        }
    )


class FirstTwoRule:
    """Match the first two events available in one zone."""

    rule_id = "TEST_TWO_EVENTS"
    confidence_score = 0.9

    def match(self, events):
        return events[:2] if len(events) >= 2 else None


class OutsideWindowRule:
    """Return an invalid event to verify engine containment checks."""

    rule_id = "TEST_INVALID"
    confidence_score = 0.5

    def match(self, events):
        return (make_event(99, 0),)


class InvalidConfidenceRule:
    """Expose an invalid confidence score."""

    rule_id = "TEST_CONFIDENCE"
    confidence_score = 1.1

    def match(self, events):
        return None


class CorrelationEngineTests(unittest.TestCase):
    """Verify buffering, purge, isolation, linking and deduplication."""

    def test_matches_and_links_all_source_events(self) -> None:
        correlation_id = UUID(int=500)
        engine = CorrelationEngine(
            60,
            rules=[FirstTwoRule()],
            uuid_factory=lambda: correlation_id,
            now_factory=lambda: START,
        )

        self.assertEqual(engine.process(make_event(1, 0)), ())
        results = engine.process(make_event(2, 10))

        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.correlation_id, correlation_id)
        self.assertEqual(result.event_ids, (UUID(int=1), UUID(int=2)))
        self.assertEqual(result.rule_triggered, "TEST_TWO_EVENTS")
        self.assertEqual(result.confidence_score, 0.9)
        self.assertTrue(
            all(
                event.correlation_id == correlation_id
                for event in result.events
            )
        )
        self.assertEqual(
            engine.events_for("1234", "01"),
            result.events,
        )

    def test_does_not_emit_the_same_correlation_twice(self) -> None:
        engine = CorrelationEngine(60, rules=[FirstTwoRule()])
        engine.process(make_event(1, 0))
        self.assertEqual(len(engine.process(make_event(2, 1))), 1)

        self.assertEqual(engine.process(make_event(3, 2)), ())

    def test_purges_expired_but_keeps_boundary_event(self) -> None:
        engine = CorrelationEngine(60)
        engine.process(make_event(1, 0))
        engine.process(make_event(2, 60))

        self.assertEqual(len(engine.events_for("1234", "01")), 2)
        removed = engine.purge_expired(START + timedelta(seconds=61))

        self.assertEqual(removed, 1)
        self.assertEqual(
            engine.events_for("1234", "01"),
            (make_event(2, 60),),
        )

    def test_late_event_cannot_reopen_an_expired_window(self) -> None:
        engine = CorrelationEngine(60)
        engine.process(make_event(2, 100))
        engine.process(make_event(1, 0))

        self.assertEqual(
            engine.events_for("1234", "01"),
            (make_event(2, 100),),
        )

    def test_isolates_windows_by_account_and_partition(self) -> None:
        engine = CorrelationEngine(60, rules=[FirstTwoRule()])

        self.assertEqual(engine.process(make_event(1, 0)), ())
        self.assertEqual(
            engine.process(make_event(2, 1, zone_partition="02")),
            (),
        )
        self.assertEqual(
            engine.process(make_event(3, 2, account_id="5678")),
            (),
        )

    def test_rejects_invalid_configuration_and_rule_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            CorrelationEngine(0)
        with self.assertRaisesRegex(ValueError, "confidence"):
            CorrelationEngine(60, rules=[InvalidConfidenceRule()])

        engine = CorrelationEngine(60, rules=[OutsideWindowRule()])
        with self.assertRaisesRegex(ValueError, "outside"):
            engine.process(make_event(1, 0))

    def test_rejects_naive_purge_and_correlation_clocks(self) -> None:
        engine = CorrelationEngine(60)
        with self.assertRaisesRegex(ValueError, "timezone"):
            engine.purge_expired(datetime(2026, 10, 12))

        engine = CorrelationEngine(
            60,
            rules=[FirstTwoRule()],
            now_factory=lambda: datetime(2026, 10, 12),
        )
        engine.process(make_event(1, 0))
        with self.assertRaisesRegex(ValueError, "timezone"):
            engine.process(make_event(2, 1))
