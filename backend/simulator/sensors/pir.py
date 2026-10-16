"""PIR sensor model based on the temperature-dependent detection formula."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from random import Random
from typing import Any, Callable, Generator

import simpy

from backend.core.risk_calendar import RiskCalendar


@dataclass
class PIRSensor:
    """Simulate a passive infrared sensor with thermal sensitivity."""

    p_base: float
    alpha: float
    body_temperature: float = 36.5
    ambient_temperature: float = 25.0
    rng: Random = field(default_factory=Random, repr=False, compare=False)
    risk_calendar: RiskCalendar | None = field(default=None, repr=False)
    now_factory: Callable[[], datetime] = field(
        default=lambda: datetime.now(timezone.utc), repr=False, compare=False,
    )

    def __post_init__(self) -> None:
        """Reject parameters outside the mathematical model domain."""
        if not 0.0 <= self.p_base <= 1.0:
            raise ValueError("p_base must be between 0 and 1")
        if not math.isfinite(self.alpha) or self.alpha < 0.0:
            raise ValueError("alpha must be a finite non-negative value")
        self._validate_temperature(self.body_temperature)
        self._validate_temperature(self.ambient_temperature)

    @staticmethod
    def _validate_temperature(value: float) -> None:
        if not math.isfinite(value):
            raise ValueError("temperature must be finite")

    @classmethod
    def from_settings(
        cls,
        settings: dict[str, Any],
        rng: Random | None = None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> "PIRSensor":
        """Create the model from the central ``sensors.pir`` settings."""
        config = settings["sensors"]["pir"]
        return cls(
            p_base=float(config["p_base"]),
            alpha=float(config["alpha"]),
            body_temperature=float(config["body_temperature"]),
            ambient_temperature=float(config["t_ambient_default"]),
            rng=rng or Random(),
            risk_calendar=RiskCalendar.from_settings(settings),
            now_factory=now_factory or (lambda: datetime.now(timezone.utc)),
        )

    def detection_probability(
        self,
        ambient_temperature: float | None = None,
        *, at: datetime | None = None,
    ) -> float:
        """Apply the current risk factor to alpha, keeping the base model."""
        temperature = (
            self.ambient_temperature
            if ambient_temperature is None
            else ambient_temperature
        )
        self._validate_temperature(temperature)
        delta = abs(self.body_temperature - temperature)
        multiplier = 1.0
        if self.risk_calendar is not None:
            instant = at if at is not None else self.now_factory()
            risk = self.risk_calendar.evaluate(instant)
            multiplier = risk.pir_alpha_multiplier
        return self.p_base * (1.0 - math.exp(-self.alpha * delta * multiplier))

    def detect(self, ambient_temperature: float | None = None,
               *, at: datetime | None = None) -> bool:
        """Sample whether the PIR detects a target at the given temperature."""
        probability = self.detection_probability(ambient_temperature, at=at)
        return self.rng.random() < probability

    def sense(
        self,
        environment: simpy.Environment,
        delay_seconds: float = 0.0,
        ambient_temperature: float | None = None,
    ) -> Generator[simpy.Event, Any, bool]:
        """Wait in simulated time and return the sampled detection result."""
        if not math.isfinite(delay_seconds) or delay_seconds < 0.0:
            raise ValueError("delay_seconds must be finite and non-negative")
        yield environment.timeout(delay_seconds)
        return self.detect(ambient_temperature)
