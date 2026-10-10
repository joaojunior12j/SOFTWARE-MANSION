"""Tests for the Sprint 1 camera IVA virtual-line model."""

import math
import unittest

import simpy

from backend.simulator.camera_iva import CameraIVA


class CameraIVATests(unittest.TestCase):
    """Verify finite-segment crossing detection and simulated latency."""

    def setUp(self) -> None:
        self.camera = CameraIVA(line_start=(0.0, -1.0), line_end=(0.0, 1.0))

    def test_detects_crossing_in_both_directions(self) -> None:
        self.assertTrue(
            self.camera.crossed_line((-1.0, 0.0), (1.0, 0.0))
        )
        self.assertTrue(
            self.camera.crossed_line((1.0, 0.0), (-1.0, 0.0))
        )

    def test_does_not_detect_movement_on_same_side(self) -> None:
        self.assertFalse(
            self.camera.crossed_line((-2.0, 0.0), (-1.0, 0.5))
        )

    def test_does_not_detect_crossing_outside_finite_line(self) -> None:
        self.assertFalse(
            self.camera.crossed_line((-1.0, 2.0), (1.0, 2.0))
        )

    def test_touching_or_standing_on_line_is_not_a_crossing(self) -> None:
        self.assertFalse(
            self.camera.crossed_line((-1.0, 0.0), (0.0, 0.0))
        )
        self.assertFalse(
            self.camera.crossed_line((0.0, 0.0), (0.0, 0.0))
        )

    def test_sense_advances_simulated_time(self) -> None:
        environment = simpy.Environment()
        process = environment.process(
            self.camera.sense(
                environment,
                previous=(-1.0, 0.0),
                current=(1.0, 0.0),
                delay_seconds=0.25,
            )
        )

        environment.run()

        self.assertEqual(environment.now, 0.25)
        self.assertTrue(process.value)

    def test_rejects_invalid_geometry_and_delay(self) -> None:
        with self.assertRaises(ValueError):
            CameraIVA((0.0, 0.0), (0.0, 0.0))
        with self.assertRaises(ValueError):
            CameraIVA((0.0, math.inf), (1.0, 0.0))

        environment = simpy.Environment()
        process = environment.process(
            self.camera.sense(environment, (-1.0, 0.0), (1.0, 0.0), -1.0)
        )
        with self.assertRaises(ValueError):
            environment.run()
        self.assertTrue(process.triggered)
