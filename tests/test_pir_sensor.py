"""Tests for the Sprint 1 PIR mathematical and SimPy model."""

import math
from random import Random
import unittest

import simpy

from backend.simulator.sensors.pir import PIRSensor


class PIRSensorTests(unittest.TestCase):
    """Verify the documented detection equation and simulated timing."""

    def setUp(self) -> None:
        self.sensor = PIRSensor(
            p_base=0.97,
            alpha=0.35,
            rng=Random(1),
        )

    def test_probability_matches_master_equation(self) -> None:
        expected = 0.97 * (1.0 - math.exp(-0.35 * abs(36.5 - 25.0)))

        self.assertAlmostEqual(
            self.sensor.detection_probability(25.0),
            expected,
        )

    def test_probability_falls_to_zero_at_body_temperature(self) -> None:
        self.assertEqual(self.sensor.detection_probability(36.5), 0.0)
        self.assertFalse(self.sensor.detect(36.5))

    def test_probability_is_symmetric_around_body_temperature(self) -> None:
        below = self.sensor.detection_probability(30.0)
        above = self.sensor.detection_probability(43.0)

        self.assertAlmostEqual(below, above)

    def test_seeded_detection_is_reproducible(self) -> None:
        self.assertTrue(self.sensor.detect(25.0))

    def test_sense_advances_simulated_time(self) -> None:
        environment = simpy.Environment()
        process = environment.process(
            self.sensor.sense(environment, 2.0, 36.5)
        )

        environment.run()

        self.assertEqual(environment.now, 2.0)
        self.assertFalse(process.value)

    def test_from_settings_uses_central_configuration(self) -> None:
        settings = {
            "sensors": {
                "pir": {
                    "p_base": 0.97,
                    "alpha": 0.35,
                    "body_temperature": 36.5,
                    "t_ambient_default": 25.0,
                }
            }
        }

        sensor = PIRSensor.from_settings(settings, Random(2))

        self.assertEqual(sensor.ambient_temperature, 25.0)

    def test_rejects_invalid_parameters(self) -> None:
        with self.assertRaises(ValueError):
            PIRSensor(p_base=1.1, alpha=0.35)
        with self.assertRaises(ValueError):
            PIRSensor(p_base=0.97, alpha=-0.1)
        with self.assertRaises(ValueError):
            self.sensor.detection_probability(math.inf)

    def test_rejects_invalid_delay(self) -> None:
        environment = simpy.Environment()
        process = environment.process(self.sensor.sense(environment, -1.0))

        with self.assertRaises(ValueError):
            environment.run()
        self.assertTrue(process.triggered)
