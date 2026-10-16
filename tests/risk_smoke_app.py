"""Isolated smoke-only API clock, supplied through a local temporary file.

Run via the Day 18 browser smoke, never as the production entry point.
"""

from datetime import datetime
import os
from pathlib import Path

from backend.api.main import create_app
from tests.test_api import FakeAlarmRepository, SETTINGS
from tests.test_risk_calendar import CONFIG


def create_smoke_app():
    """Build an isolated risk API with no MQTT bridge or database writes."""
    clock_file = Path(os.environ['PSIM_RISK_SMOKE_CLOCK'])

    def clock():
        return datetime.fromisoformat(clock_file.read_text(encoding='utf-8'))

    return create_app(
        {**SETTINGS, 'risk_calendar': CONFIG},
        alarm_repository=FakeAlarmRepository(),
        start_services=False, risk_clock=clock,
    )
