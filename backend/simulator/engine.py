"""Core SimPy runner shared by the simulator command-line scenarios."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Generator, Mapping, TypeAlias

import simpy

from backend.api.schemas import AlarmEvent


@dataclass(frozen=True)
class ScenarioContext:
    """Runtime values supplied to every simulator scenario."""

    account_id: str
    speed_multiplier: float = 1.0

    def __post_init__(self) -> None:
        """Reject incomplete account and invalid simulation speed values."""
        if not self.account_id.strip():
            raise ValueError("account_id must not be empty")
        if (
            not math.isfinite(self.speed_multiplier)
            or self.speed_multiplier <= 0.0
        ):
            raise ValueError("speed_multiplier must be finite and positive")

    def delay(self, scenario_seconds: float) -> float:
        """Convert scenario time into accelerated SimPy time."""
        if not math.isfinite(scenario_seconds) or scenario_seconds < 0.0:
            raise ValueError(
                "scenario_seconds must be finite and non-negative"
            )
        return scenario_seconds / self.speed_multiplier


ScenarioProcess: TypeAlias = Generator[
    simpy.Event,
    Any,
    list[AlarmEvent],
]
Scenario: TypeAlias = Callable[
    [simpy.Environment, ScenarioContext],
    ScenarioProcess,
]


@dataclass(frozen=True)
class SimulationResult:
    """Completed scenario data returned to CLI or API callers."""

    scenario: str
    elapsed_seconds: float
    events: tuple[AlarmEvent, ...]


class SimulationEngine:
    """Run registered scenario generators in an isolated SimPy environment."""

    def __init__(self, scenarios: Mapping[str, Scenario]) -> None:
        self._scenarios = dict(scenarios)

    @property
    def available_scenarios(self) -> tuple[str, ...]:
        """Return registered scenario names in stable display order."""
        return tuple(sorted(self._scenarios))

    def run(
        self,
        scenario: str,
        account_id: str,
        speed_multiplier: float = 1.0,
    ) -> SimulationResult:
        """Execute one registered scenario until all its events complete."""
        try:
            handler = self._scenarios[scenario]
        except KeyError as error:
            raise ValueError(f"unknown scenario: {scenario}") from error

        context = ScenarioContext(account_id, speed_multiplier)
        environment = simpy.Environment()
        process = environment.process(handler(environment, context))
        environment.run()
        return SimulationResult(
            scenario=scenario,
            elapsed_seconds=float(environment.now),
            events=tuple(process.value),
        )
