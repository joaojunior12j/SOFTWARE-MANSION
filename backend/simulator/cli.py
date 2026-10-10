"""Command-line interface for registered PSIM Mansion scenarios."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import math
from typing import Any

from backend.core.settings import load_settings
from backend.simulator.engine import Scenario, SimulationEngine
from backend.simulator.scenarios import SCENARIOS


def positive_float(value: str) -> float:
    """Parse an argparse value that must be finite and greater than zero."""
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise argparse.ArgumentTypeError(
            "must be finite and greater than zero"
        )
    return parsed


def build_parser(settings: Mapping[str, Any]) -> argparse.ArgumentParser:
    """Build the documented simulator command-line contract."""
    parser = argparse.ArgumentParser(
        description="Executa cenários SimPy do PSIM Mansion.",
    )
    parser.add_argument(
        "--scenario",
        default=settings["simulator"]["default_scenario"],
        help="nome do cenário registrado",
    )
    parser.add_argument(
        "--account",
        default=settings["system"]["account_id"],
        help="identificador da conta/mansão",
    )
    parser.add_argument(
        "--speed",
        type=positive_float,
        default=float(settings["simulator"]["speed_multiplier"]),
        help="multiplicador positivo da velocidade simulada",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="lista os cenários disponíveis sem executá-los",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    settings: Mapping[str, Any] | None = None,
    scenarios: Mapping[str, Scenario] | None = None,
) -> int:
    """Parse arguments, execute the selected scenario and print a summary."""
    resolved_settings = settings or load_settings()
    registered = SCENARIOS if scenarios is None else scenarios
    engine = SimulationEngine(registered)
    parser = build_parser(resolved_settings)
    args = parser.parse_args(argv)

    if args.list_scenarios:
        for name in engine.available_scenarios:
            print(name)
        return 0

    try:
        result = engine.run(args.scenario, args.account, args.speed)
    except ValueError as error:
        available = ", ".join(engine.available_scenarios) or "nenhum"
        parser.error(f"{error}; disponíveis: {available}")

    print(
        f"scenario={result.scenario} account={args.account} "
        f"events={len(result.events)} elapsed={result.elapsed_seconds:.3f}s"
    )
    return 0
