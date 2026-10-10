"""Camera IVA model for detecting a virtual-line crossing."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Generator, TypeAlias

import simpy


Point: TypeAlias = tuple[float, float]


def _orientation(start: Point, end: Point, point: Point) -> float:
    """Return the signed area used to identify a point's line side."""
    return (
        (end[0] - start[0]) * (point[1] - start[1])
        - (end[1] - start[1]) * (point[0] - start[0])
    )


def _validate_point(point: Point) -> None:
    if len(point) != 2 or any(not math.isfinite(value) for value in point):
        raise ValueError("points must contain two finite coordinates")


@dataclass(frozen=True)
class CameraIVA:
    """Detect strict crossings of a finite virtual line segment."""

    line_start: Point
    line_end: Point

    def __post_init__(self) -> None:
        """Require a valid, non-degenerate virtual line."""
        _validate_point(self.line_start)
        _validate_point(self.line_end)
        if self.line_start == self.line_end:
            raise ValueError("virtual line endpoints must be distinct")

    def crossed_line(self, previous: Point, current: Point) -> bool:
        """Return true when movement crosses the configured line segment."""
        _validate_point(previous)
        _validate_point(current)
        if previous == current:
            return False

        previous_side = _orientation(
            self.line_start,
            self.line_end,
            previous,
        )
        current_side = _orientation(
            self.line_start,
            self.line_end,
            current,
        )
        if previous_side * current_side >= 0.0:
            return False

        line_start_side = _orientation(previous, current, self.line_start)
        line_end_side = _orientation(previous, current, self.line_end)
        return line_start_side * line_end_side <= 0.0

    def sense(
        self,
        environment: simpy.Environment,
        previous: Point,
        current: Point,
        delay_seconds: float = 0.0,
    ) -> Generator[simpy.Event, Any, bool]:
        """Wait in simulated time and evaluate one movement segment."""
        if not math.isfinite(delay_seconds) or delay_seconds < 0.0:
            raise ValueError("delay_seconds must be finite and non-negative")
        crossed = self.crossed_line(previous, current)
        yield environment.timeout(delay_seconds)
        return crossed
