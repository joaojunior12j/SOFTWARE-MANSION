"""Read-only risk policy status for the local HMI."""

from dataclasses import asdict
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel


router = APIRouter(prefix='/api', tags=['risco'])


class RiskRead(BaseModel):
    """Separate status contract; canonical alarm payload stays untouched."""

    mode: Literal['STANDARD', 'ELEVATED', 'DISABLED']
    reason: Literal['outside_schedule', 'configured_date', 'weekly_hour',
                    'disabled']
    timezone: str
    evaluated_at: datetime
    local_time: datetime
    pir_alpha_multiplier: float
    scope: Literal['SIMULATOR_PIR']


@router.get('/risco', response_model=RiskRead)
async def risk_status(request: Request) -> RiskRead:
    """Evaluate configured policy with server time, never a client override."""
    state = request.app.state
    snapshot = state.risk_calendar.evaluate(state.risk_clock())
    return RiskRead(**asdict(snapshot))
