"""Canonical message contracts for the PSIM Mansion event bus."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


SourceType = Literal[
    "PERIMETER_SENSOR",
    "CAMERA",
    "ALARM_PANEL",
    "SIMULATOR",
]
EventStatus = Literal[
    "ACTIVE",
    "RESTORED",
    "TAMPER",
    "DISCONNECTED",
    "TIMEOUT_SIA_DC09",
]
PriorityLevel = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
AlarmState = Literal[
    "UNACKNOWLEDGED",
    "ACKNOWLEDGED",
    "RESTORED",
    "CLEARED",
    "SHELVED",
]


class AlarmEvent(BaseModel):
    """Fixed JSON payload accepted by every producer and consumer."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    timestamp: datetime
    account_id: str
    source_type: SourceType
    device_hardware_id: str
    zone_partition: str
    zone_number: int
    sia_code: str
    event_status: EventStatus
    priority_level: PriorityLevel
    correlation_id: UUID | None = None

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_include_timezone(cls, value: datetime) -> datetime:
        """Reject ambiguous timestamps without an explicit UTC offset."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone offset")
        return value


class AlarmRead(BaseModel):
    """Operator-facing alarm representation returned by the API."""

    model_config = ConfigDict(extra="forbid")

    alarm_id: UUID
    correlation_id: UUID | None = None
    title: str
    description: str | None = None
    priority_level: PriorityLevel
    state: AlarmState
    zone_partition: str | None = None
    triggered_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: UUID | None = None
    cleared_at: datetime | None = None
    rule_triggered: str | None = None
    sia_codes: list[str] = Field(default_factory=list)


class AlarmAcknowledgeRequest(BaseModel):
    """Operator identity required for the ISA-18.2 acknowledge action."""

    model_config = ConfigDict(extra="forbid")

    acknowledged_by: UUID


class SystemStatus(BaseModel):
    """Live connectivity state displayed by the supervisory HMI."""

    mqtt_online: bool
