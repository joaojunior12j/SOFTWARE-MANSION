"""Alarm query routes for the supervisory HMI."""

from fastapi import APIRouter, Request

from backend.api.schemas import AlarmRead


router = APIRouter(prefix="/api/alarmes", tags=["alarmes"])


@router.get("/ativos", response_model=list[AlarmRead])
async def list_active_alarms(request: Request) -> list[AlarmRead]:
    """Return active alarms ordered by priority and trigger time."""
    repository = request.app.state.alarm_repository
    return await repository.list_active()
