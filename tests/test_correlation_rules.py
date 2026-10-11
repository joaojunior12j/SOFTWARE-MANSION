"""Tests for Sprint 1 CEP rules R01 and R02."""

from datetime import datetime, timedelta, timezone
from uuid import UUID
import unittest

from backend.api.schemas import AlarmEvent
from backend.core.correlation_rules import (
    JammerRule,
    MultiSensorRule,
    build_rules,
)
from tests.test_event_contract import CANONICAL_EVENT


START = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def event(
    number: int,
    seconds: float,
    source_type: str,
    status: str,
    sia_code: str,
    device: str,
) -> AlarmEvent:
    """Build one deterministic event for rule evaluation."""
    return AlarmEvent.model_validate(
        {
            **CANONICAL_EVENT,
            "event_id": UUID(int=number),
            "timestamp": START + timedelta(seconds=seconds),
            "source_type": source_type,
            "event_status": status,
            "sia_code": sia_code,
            "device_hardware_id": device,
        }
    )


class CorrelationRuleTests(unittest.TestCase):
    """Verify exact documented conditions and temporal limits."""

    def test_r01_matches_jammer_sequence_within_fifteen_seconds(self) -> None:
        events = (
            event(1, 0, "CAMERA", "DISCONNECTED", "TA", "CAM-1"),
            event(2, 5, "ALARM_PANEL", "TIMEOUT_SIA_DC09", "RP", "PANEL"),
            event(3, 10, "PERIMETER_SENSOR", "ACTIVE", "BA", "PIR-1"),
        )

        matched = JammerRule(15).match(events)

        self.assertEqual(tuple(matched), events)

    def test_r01_rejects_incomplete_or_expired_sequence(self) -> None:
        events = (
            event(1, 0, "CAMERA", "DISCONNECTED", "TA", "CAM-1"),
            event(2, 5, "ALARM_PANEL", "TIMEOUT_SIA_DC09", "RP", "PANEL"),
            event(3, 16, "PERIMETER_SENSOR", "ACTIVE", "BA", "PIR-1"),
        )

        self.assertIsNone(JammerRule(15).match(events))
        self.assertIsNone(JammerRule(15).match(events[:2]))

    def test_r02_requires_three_distinct_intrusion_devices(self) -> None:
        events = (
            event(1, 0, "PERIMETER_SENSOR", "ACTIVE", "SA", "SEISMIC"),
            event(2, 2, "PERIMETER_SENSOR", "ACTIVE", "BA", "BEAM"),
            event(3, 4, "PERIMETER_SENSOR", "ACTIVE", "BA", "PIR"),
            event(4, 5, "PERIMETER_SENSOR", "ACTIVE", "BA", "PIR"),
        )

        matched = MultiSensorRule(60).match(events)

        self.assertEqual(len(matched), 3)
        self.assertEqual(
            {item.device_hardware_id for item in matched},
            {"SEISMIC", "BEAM", "PIR"},
        )
        self.assertEqual(matched[-1].event_id, UUID(int=4))

    def test_r02_rejects_events_outside_sixty_seconds(self) -> None:
        events = (
            event(1, 0, "PERIMETER_SENSOR", "ACTIVE", "SA", "SEISMIC"),
            event(2, 2, "PERIMETER_SENSOR", "ACTIVE", "BA", "BEAM"),
            event(3, 61, "PERIMETER_SENSOR", "ACTIVE", "BA", "PIR"),
        )

        self.assertIsNone(MultiSensorRule(60).match(events))

    def test_rules_ignore_events_already_correlated(self) -> None:
        correlated = event(
            1,
            0,
            "PERIMETER_SENSOR",
            "ACTIVE",
            "SA",
            "SEISMIC",
        ).model_copy(update={"correlation_id": UUID(int=99)})
        events = (
            correlated,
            event(2, 2, "PERIMETER_SENSOR", "ACTIVE", "BA", "BEAM"),
            event(3, 4, "PERIMETER_SENSOR", "ACTIVE", "BA", "PIR"),
        )

        self.assertIsNone(MultiSensorRule(60).match(events))

    def test_build_rules_uses_central_configuration(self) -> None:
        rules = build_rules(
            {
                "correlation_engine": {
                    "jammer_window_seconds": 15,
                    "window_seconds": 60,
                }
            }
        )

        self.assertEqual(
            [rule.rule_id for rule in rules],
            ["R01_JAMMER", "R02_MULTI_SENSOR"],
        )

    def test_rules_reject_non_positive_windows(self) -> None:
        with self.assertRaises(ValueError):
            JammerRule(0)
        with self.assertRaises(ValueError):
            MultiSensorRule(-1)
