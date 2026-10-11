"""Tests for the complete Sprint 1 RF-jammer scenario."""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID
import unittest

from backend.simulator.engine import SimulationEngine
from backend.simulator.scenarios.rf_jammer import build_rf_jammer


SETTINGS = {
    "correlation_engine": {"jammer_window_seconds": 15},
    "simulator": {
        "scenarios": {
            "rf_jammer": {
                "random_seed": 1,
                "timings_seconds": {
                    "camera_offline": 0,
                    "sia_timeout": 5,
                    "pir_active": 10,
                },
                "devices": {
                    "camera": {
                        "hardware_id": "CAMERA-PERIMETRO-NORTE",
                        "zone_partition": "01",
                        "zone_number": 3,
                    },
                    "alarm_panel": {
                        "hardware_id": "CENTRAL-SIA-PRINCIPAL",
                        "zone_partition": "01",
                        "zone_number": 0,
                    },
                    "pir": {
                        "hardware_id": "PIR-PERIMETRO-NORTE",
                        "zone_partition": "01",
                        "zone_number": 2,
                    },
                },
            }
        }
    },
    "sensors": {
        "pir": {
            "p_base": 0.97,
            "alpha": 0.35,
            "body_temperature": 36.5,
            "t_ambient_default": 25.0,
        }
    },
}


class UUIDSequence:
    """Return deterministic UUIDs for payload assertions."""

    def __init__(self) -> None:
        self.value = 10

    def __call__(self) -> UUID:
        self.value += 1
        return UUID(int=self.value)


class RFJammerTests(unittest.TestCase):
    """Verify the three inputs required by correlation rule R01."""

    def build_engine(self, settings=SETTINGS):
        start = datetime(2026, 10, 11, 23, 0, tzinfo=timezone.utc)
        scenario = build_rf_jammer(
            settings,
            now_factory=lambda: start,
            uuid_factory=UUIDSequence(),
        )
        return SimulationEngine({"rf_jammer": scenario}), start

    def test_generates_r01_inputs_inside_fifteen_seconds(self) -> None:
        engine, start = self.build_engine()
        published = []

        result = engine.run("rf_jammer", "1234", event_sink=published.append)

        self.assertEqual(result.elapsed_seconds, 10.0)
        self.assertEqual(tuple(published), result.events)
        self.assertEqual(len(result.events), 3)
        self.assertEqual(
            [event.source_type for event in result.events],
            ["CAMERA", "ALARM_PANEL", "PERIMETER_SENSOR"],
        )
        self.assertEqual(
            [event.event_status for event in result.events],
            ["DISCONNECTED", "TIMEOUT_SIA_DC09", "ACTIVE"],
        )
        self.assertEqual(
            [event.sia_code for event in result.events],
            ["TA", "RP", "BA"],
        )
        self.assertEqual(
            {
                event.zone_partition
                for event in result.events
            },
            {"01"},
        )
        offsets = [
            (event.timestamp - start).total_seconds()
            for event in result.events
        ]
        self.assertEqual(offsets, [0.0, 5.0, 10.0])
        self.assertLessEqual(offsets[-1] - offsets[0], 15.0)

    def test_every_event_uses_exact_fixed_payload(self) -> None:
        engine, _ = self.build_engine()

        result = engine.run("rf_jammer", "1234")

        expected_keys = {
            "event_id",
            "timestamp",
            "account_id",
            "source_type",
            "device_hardware_id",
            "zone_partition",
            "zone_number",
            "sia_code",
            "event_status",
            "priority_level",
            "correlation_id",
        }
        for event in result.events:
            self.assertEqual(set(event.model_dump()), expected_keys)
            self.assertIsNone(event.correlation_id)

    def test_speed_changes_runtime_not_event_timestamps(self) -> None:
        engine, start = self.build_engine()

        result = engine.run("rf_jammer", "1234", speed_multiplier=2.0)

        self.assertEqual(result.elapsed_seconds, 5.0)
        self.assertEqual(
            (result.events[-1].timestamp - start).total_seconds(),
            10.0,
        )

    def test_rejects_events_outside_r01_window(self) -> None:
        settings = deepcopy(SETTINGS)
        timings = settings["simulator"]["scenarios"]["rf_jammer"][
            "timings_seconds"
        ]
        timings["pir_active"] = 16

        with self.assertRaisesRegex(ValueError, "exceed"):
            build_rf_jammer(settings)

    def test_rejects_unordered_or_negative_timings(self) -> None:
        for camera_offset, timeout_offset in ((-1, 5), (6, 5)):
            settings = deepcopy(SETTINGS)
            timings = settings["simulator"]["scenarios"]["rf_jammer"][
                "timings_seconds"
            ]
            timings["camera_offline"] = camera_offset
            timings["sia_timeout"] = timeout_offset

            with self.assertRaisesRegex(ValueError, "ordered"):
                build_rf_jammer(settings)

    def test_requires_timezone_aware_clock(self) -> None:
        scenario = build_rf_jammer(
            SETTINGS,
            now_factory=lambda: datetime(2026, 10, 11, 23, 0),
        )
        engine = SimulationEngine({"rf_jammer": scenario})

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            engine.run("rf_jammer", "1234")

    def test_fails_when_pir_does_not_detect(self) -> None:
        settings = deepcopy(SETTINGS)
        settings["sensors"]["pir"]["t_ambient_default"] = 36.5
        engine, _ = self.build_engine(settings)

        with self.assertRaisesRegex(RuntimeError, "PIR did not detect"):
            engine.run("rf_jammer", "1234")
