"""Tests for the complete Sprint 1 wall-jump scenario."""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID
import unittest

from backend.simulator.engine import SimulationEngine
from backend.simulator.scenarios.wall_jump import build_wall_jump


SETTINGS = {
    "simulator": {
        "scenarios": {
            "wall_jump": {
                "random_seed": 1,
                "beam_block_ms": 180,
                "timings_seconds": {
                    "seismic": 0,
                    "beam": 2,
                    "pir": 4,
                    "camera": 6,
                },
                "camera_line": {
                    "start": [0.0, -1.0],
                    "end": [0.0, 1.0],
                },
                "camera_movement": {
                    "previous": [-1.0, 0.0],
                    "current": [1.0, 0.0],
                },
                "devices": {
                    "seismic": {
                        "hardware_id": "SEISMIC-MURO-NORTE",
                        "zone_partition": "01",
                        "zone_number": 1,
                    },
                    "beam": {
                        "hardware_id": "BEAM-MURO-NORTE",
                        "zone_partition": "01",
                        "zone_number": 1,
                    },
                    "pir": {
                        "hardware_id": "PIR-PERIMETRO-NORTE",
                        "zone_partition": "01",
                        "zone_number": 2,
                    },
                    "camera": {
                        "hardware_id": "CAMERA-PERIMETRO-NORTE",
                        "zone_partition": "01",
                        "zone_number": 3,
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
        },
        "beam_iv": {
            "suspicious_min_block_ms": 50,
            "min_block_ms": 100,
        },
    },
}


class UUIDSequence:
    """Return deterministic UUIDs for payload assertions."""

    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> UUID:
        self.value += 1
        return UUID(int=self.value)


class WallJumpTests(unittest.TestCase):
    """Verify the four canonical events and documented timeline."""

    def build_engine(self, settings=SETTINGS):
        start = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
        scenario = build_wall_jump(
            settings,
            now_factory=lambda: start,
            uuid_factory=UUIDSequence(),
        )
        return SimulationEngine({"wall_jump": scenario}), start

    def test_generates_four_events_in_documented_order(self) -> None:
        engine, start = self.build_engine()
        published = []

        result = engine.run("wall_jump", "1234", event_sink=published.append)

        self.assertEqual(result.elapsed_seconds, 6.0)
        self.assertEqual(len(result.events), 4)
        self.assertEqual(tuple(published), result.events)
        self.assertEqual(
            [event.sia_code for event in result.events],
            ["SA", "BA", "BA", "BA"],
        )
        self.assertEqual(
            [event.priority_level for event in result.events],
            ["HIGH", "CRITICAL", "CRITICAL", "CRITICAL"],
        )
        self.assertEqual(result.events[-1].source_type, "CAMERA")
        self.assertEqual(
            [
                (event.timestamp - start).total_seconds()
                for event in result.events
            ],
            [0.0, 2.0, 4.0, 6.0],
        )

    def test_every_event_uses_exact_fixed_payload(self) -> None:
        engine, _ = self.build_engine()

        result = engine.run("wall_jump", "1234")

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
            self.assertEqual(event.account_id, "1234")
            self.assertEqual(event.event_status, "ACTIVE")
            self.assertIsNone(event.correlation_id)

    def test_speed_changes_runtime_not_event_timestamps(self) -> None:
        engine, start = self.build_engine()

        result = engine.run("wall_jump", "1234", speed_multiplier=2.0)

        self.assertEqual(result.elapsed_seconds, 3.0)
        self.assertEqual(
            (result.events[-1].timestamp - start).total_seconds(),
            6.0,
        )

    def test_fails_if_beam_configuration_does_not_alarm(self) -> None:
        settings = deepcopy(SETTINGS)
        settings["sensors"]["beam_iv"]["min_block_ms"] = 200
        engine, _ = self.build_engine(settings)

        with self.assertRaisesRegex(RuntimeError, "beam interruption"):
            engine.run("wall_jump", "1234")

    def test_requires_timezone_aware_clock(self) -> None:
        scenario = build_wall_jump(
            SETTINGS,
            now_factory=lambda: datetime(2026, 10, 11, 12, 0),
        )
        engine = SimulationEngine({"wall_jump": scenario})

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            engine.run("wall_jump", "1234")
