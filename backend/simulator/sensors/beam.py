"""Active infrared beam model with the mandatory blocking-time filter."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Generator

import simpy


class BeamDecision(str, Enum):
    """Classification defined by the beam interruption duration."""

    IGNORE = "IGNORE"
    SUSPICIOUS = "SUSPICIOUS"
    ALARM = "ALARM"


@dataclass(frozen=True)
class BeamSensor:
    """Classify short, suspicious and alarm-worthy beam interruptions."""

    suspicious_min_block_ms: float = 50.0
    min_block_ms: float = 100.0

    def __post_init__(self) -> None:
        """Validate the ordered thresholds specified by the master document."""
        values = (self.suspicious_min_block_ms, self.min_block_ms)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("beam thresholds must be finite")
        if self.suspicious_min_block_ms < 0.0:
            raise ValueError("beam thresholds must be non-negative")
        if self.min_block_ms < self.suspicious_min_block_ms:
            raise ValueError("min_block_ms must not precede suspicious range")

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "BeamSensor":
        """Create the model from the central ``sensors.beam_iv`` settings."""
        config = settings["sensors"]["beam_iv"]
        return cls(
            suspicious_min_block_ms=float(
                config["suspicious_min_block_ms"]
            ),
            min_block_ms=float(config["min_block_ms"]),
        )

    def classify(self, block_duration_ms: float) -> BeamDecision:
        """Classify an interruption using the 50 ms and 100 ms limits."""
        if not math.isfinite(block_duration_ms) or block_duration_ms < 0.0:
            raise ValueError(
                "block_duration_ms must be finite and non-negative"
            )
        if block_duration_ms < self.suspicious_min_block_ms:
            return BeamDecision.IGNORE
        if block_duration_ms < self.min_block_ms:
            return BeamDecision.SUSPICIOUS
        return BeamDecision.ALARM

    def sense(
        self,
        environment: simpy.Environment,
        block_duration_ms: float,
    ) -> Generator[simpy.Event, Any, BeamDecision]:
        """Advance simulated time for the blockage and return its decision."""
        decision = self.classify(block_duration_ms)
        yield environment.timeout(block_duration_ms / 1000.0)
        return decision
