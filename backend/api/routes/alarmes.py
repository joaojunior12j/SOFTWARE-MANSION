"""Alarm query routes for the supervisory HMI."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from backend.api.schemas import AlarmAcknowledgeRequest, AlarmRead
from backend.db.alarm_repository import (
    AlarmNotFoundError,
    InvalidAlarmTransitionError,
)


router = APIRouter(prefix="/api/alarmes", tags=["alarmes"])


@router.get("/ativos", response_model=list[AlarmRead])
async def list_active_alarms(request: Request) -> list[AlarmRead]:
    """Return active alarms ordered by priority and trigger time."""
    repository = request.app.state.alarm_repository
    return await repository.list_active()


@router.post("/{alarm_id}/acknowledge", response_model=AlarmRead)
async def acknowledge_alarm(
    alarm_id: UUID,
    payload: AlarmAcknowledgeRequest,
    request: Request,
) -> AlarmRead:
    """Apply the ISA-18.2 acknowledge transition for one operator."""
    repository = request.app.state.alarm_repository
    try:
        return await repository.acknowledge(
            alarm_id,
            payload.acknowledged_by,
        )
    except AlarmNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="alarm not found",
        ) from error
    except InvalidAlarmTransitionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
