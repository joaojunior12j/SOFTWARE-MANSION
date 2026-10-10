"""Tests for the Sprint 1 active infrared beam SimPy model."""

import math
import unittest

import simpy

from backend.simulator.sensors.beam import BeamDecision, BeamSensor


class BeamSensorTests(unittest.TestCase):
    """Verify every duration boundary in the documented beam filter."""

    def setUp(self) -> None:
        self.sensor = BeamSensor(
            suspicious_min_block_ms=50.0,
            min_block_ms=100.0,
        )

    def test_ignores_interruption_below_fifty_milliseconds(self) -> None:
        self.assertEqual(self.sensor.classify(49.999), BeamDecision.IGNORE)

    def test_marks_intermediate_interruption_as_suspicious(self) -> None:
        self.assertEqual(
            self.sensor.classify(50.0),
            BeamDecision.SUSPICIOUS,
        )
        self.assertEqual(
            self.sensor.classify(99.999),
            BeamDecision.SUSPICIOUS,
        )

    def test_alarms_at_one_hundred_milliseconds(self) -> None:
        self.assertEqual(self.sensor.classify(100.0), BeamDecision.ALARM)

    def test_sense_advances_for_the_actual_block_duration(self) -> None:
        environment = simpy.Environment()
        process = environment.process(self.sensor.sense(environment, 180.0))

        environment.run()

        self.assertAlmostEqual(environment.now, 0.18)
        self.assertEqual(process.value, BeamDecision.ALARM)

    def test_from_settings_uses_central_configuration(self) -> None:
        settings = {
            "sensors": {
                "beam_iv": {
                    "suspicious_min_block_ms": 50,
                    "min_block_ms": 100,
                }
            }
        }

        sensor = BeamSensor.from_settings(settings)

        self.assertEqual(sensor.classify(75), BeamDecision.SUSPICIOUS)

    def test_rejects_invalid_duration(self) -> None:
        for value in (-1.0, math.inf, math.nan):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.sensor.classify(value)

    def test_rejects_invalid_thresholds(self) -> None:
        with self.assertRaises(ValueError):
            BeamSensor(suspicious_min_block_ms=-1.0)
        with self.assertRaises(ValueError):
            BeamSensor(
                suspicious_min_block_ms=100.0,
                min_block_ms=50.0,
            )
