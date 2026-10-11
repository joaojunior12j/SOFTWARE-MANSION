"""Tests for the Sprint 1 simulator engine and command-line entry point."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import unittest

from backend.simulator.cli import main, positive_float
from backend.simulator.engine import ScenarioContext, SimulationEngine


SETTINGS = {
    "system": {"account_id": "1234"},
    "simulator": {"default_scenario": "wall_jump", "speed_multiplier": 1.0},
}


def sample_scenario(environment, context):
    """Provide a deterministic scenario used only by CLI unit tests."""
    yield environment.timeout(context.delay(6.0))
    return []


class SimulationEngineTests(unittest.TestCase):
    """Verify registry dispatch, context validation and speed control."""

    def test_runs_registered_scenario_with_speed_multiplier(self) -> None:
        engine = SimulationEngine({"wall_jump": sample_scenario})

        result = engine.run("wall_jump", "1234", speed_multiplier=2.0)

        self.assertEqual(result.scenario, "wall_jump")
        self.assertEqual(result.elapsed_seconds, 3.0)
        self.assertEqual(result.events, ())

    def test_lists_scenarios_in_stable_order(self) -> None:
        engine = SimulationEngine(
            {"wall_jump": sample_scenario, "rf_jammer": sample_scenario}
        )

        self.assertEqual(
            engine.available_scenarios,
            ("rf_jammer", "wall_jump"),
        )

    def test_rejects_unknown_scenario_and_invalid_context(self) -> None:
        engine = SimulationEngine({})
        with self.assertRaisesRegex(ValueError, "unknown scenario"):
            engine.run("wall_jump", "1234")
        with self.assertRaises(ValueError):
            ScenarioContext("", 1.0)
        with self.assertRaises(ValueError):
            ScenarioContext("1234", 0.0)

    def test_context_rejects_invalid_scenario_delay(self) -> None:
        context = ScenarioContext("1234")

        with self.assertRaises(ValueError):
            context.delay(-1.0)


class SimulatorCLITests(unittest.TestCase):
    """Verify the documented CLI arguments and operator-facing output."""

    def test_executes_documented_command_shape(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                ["--scenario", "wall_jump", "--account", "1234"],
                settings=SETTINGS,
                scenarios={"wall_jump": sample_scenario},
                event_sink=lambda event: None,
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("scenario=wall_jump account=1234", output.getvalue())

    def test_lists_available_scenarios(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                ["--list-scenarios"],
                settings=SETTINGS,
                scenarios={"wall_jump": sample_scenario},
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue().strip(), "wall_jump")

    def test_unknown_scenario_is_a_cli_error(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(
                    ["--scenario", "missing"],
                    settings=SETTINGS,
                    scenarios={},
                )

        self.assertEqual(raised.exception.code, 2)

    def test_speed_parser_rejects_invalid_values(self) -> None:
        for value in ("zero", "0", "-1", "inf", "nan"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    positive_float(value)
