"""Tests for the fixed Sprint 1 event payload."""

from datetime import datetime
import unittest

from pydantic import ValidationError

from backend.api.schemas import AlarmEvent


CANONICAL_EVENT = {
    "event_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "timestamp": "2026-10-05T21:22:00Z",
    "account_id": "1234",
    "source_type": "PERIMETER_SENSOR",
    "device_hardware_id": "PIR-ZONA-01-NORTE",
    "zone_partition": "01",
    "zone_number": 3,
    "sia_code": "BA",
    "event_status": "ACTIVE",
    "priority_level": "CRITICAL",
    "correlation_id": None,
}


class AlarmEventTests(unittest.TestCase):
    """Keep producers and consumers on the exact canonical contract."""

    def test_accepts_canonical_payload(self) -> None:
        event = AlarmEvent.model_validate(CANONICAL_EVENT)

        self.assertEqual(event.account_id, "1234")
        self.assertEqual(event.zone_number, 3)

    def test_rejects_unknown_field(self) -> None:
        payload = {**CANONICAL_EVENT, "unexpected": True}

        with self.assertRaises(ValidationError):
            AlarmEvent.model_validate(payload)

    def test_rejects_naive_timestamp(self) -> None:
        payload = {
            **CANONICAL_EVENT,
            "timestamp": datetime(2026, 10, 5, 21, 22),
        }

        with self.assertRaises(ValidationError):
            AlarmEvent.model_validate(payload)
