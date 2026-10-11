"""Deterministic RF-jammer scenario defined by the Sprint 1 master plan."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from random import Random
from typing import Any
from uuid import UUID, uuid4

import simpy

from backend.api.schemas import AlarmEvent
from backend.simulator.engine import Scenario, ScenarioContext
from backend.simulator.sensors.pir import PIRSensor


def build_rf_jammer(
    settings: Mapping[str, Any],
    now_factory: Callable[[], datetime] | None = None,
    uuid_factory: Callable[[], UUID] = uuid4,
) -> Scenario:
    """Build camera, SIA timeout and PIR events inside the R01 window."""
    scenario = settings["simulator"]["scenarios"]["rf_jammer"]
    devices = scenario["devices"]
    timings = scenario["timings_seconds"]
    ordered_offsets = [
        float(timings["camera_offline"]),
        float(timings["sia_timeout"]),
        float(timings["pir_active"]),
    ]
    window = float(settings["correlation_engine"]["jammer_window_seconds"])
    if ordered_offsets != sorted(ordered_offsets) or ordered_offsets[0] < 0:
        raise ValueError("rf_jammer timings must be non-negative and ordered")
    if ordered_offsets[-1] - ordered_offsets[0] > window:
        raise ValueError("rf_jammer events exceed the configured R01 window")

    pir = PIRSensor.from_settings(
        dict(settings),
        Random(int(scenario["random_seed"])),
    )
    clock = now_factory or (lambda: datetime.now(timezone.utc))

    def create_event(
        context: ScenarioContext,
        started_at: datetime,
        device_name: str,
        offset: float,
        source_type: str,
        sia_code: str,
        event_status: str,
        priority_level: str,
    ) -> AlarmEvent:
        device = devices[device_name]
        return AlarmEvent.model_validate(
            {
                "event_id": uuid_factory(),
                "timestamp": started_at + timedelta(seconds=offset),
                "account_id": context.account_id,
                "source_type": source_type,
                "device_hardware_id": device["hardware_id"],
                "zone_partition": device["zone_partition"],
                "zone_number": device["zone_number"],
                "sia_code": sia_code,
                "event_status": event_status,
                "priority_level": priority_level,
                "correlation_id": None,
            }
        )

    def run(
        environment: simpy.Environment,
        context: ScenarioContext,
    ):
        started_at = clock()
        if started_at.tzinfo is None or started_at.utcoffset() is None:
            raise ValueError(
                "rf_jammer clock must return a timezone-aware value"
            )
        events = []

        camera_event = create_event(
            context,
            started_at,
            "camera",
            ordered_offsets[0],
            "CAMERA",
            "TA",
            "DISCONNECTED",
            "HIGH",
        )
        events.append(camera_event)
        context.emit(camera_event)

        yield environment.timeout(
            context.delay(ordered_offsets[1] - ordered_offsets[0])
        )
        panel_event = create_event(
            context,
            started_at,
            "alarm_panel",
            ordered_offsets[1],
            "ALARM_PANEL",
            "RP",
            "TIMEOUT_SIA_DC09",
            "HIGH",
        )
        events.append(panel_event)
        context.emit(panel_event)

        yield environment.timeout(
            context.delay(ordered_offsets[2] - ordered_offsets[1])
        )
        if not pir.detect():
            raise RuntimeError("rf_jammer PIR did not detect the intruder")
        pir_event = create_event(
            context,
            started_at,
            "pir",
            ordered_offsets[2],
            "PERIMETER_SENSOR",
            "BA",
            "ACTIVE",
            "CRITICAL",
        )
        events.append(pir_event)
        context.emit(pir_event)
        return events

    return run
