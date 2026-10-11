"""Build the simulator scenario registry from central configuration."""

from collections.abc import Mapping
from typing import Any

from backend.simulator.engine import Scenario
from backend.simulator.scenarios.rf_jammer import build_rf_jammer
from backend.simulator.scenarios.wall_jump import build_wall_jump


def build_scenarios(settings: Mapping[str, Any]) -> dict[str, Scenario]:
    """Return every implemented scenario keyed by its CLI name."""
    return {
        "rf_jammer": build_rf_jammer(settings),
        "wall_jump": build_wall_jump(settings),
    }
