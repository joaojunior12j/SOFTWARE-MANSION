"""Deterministic wall-jump scenario defined by the Sprint 1 master plan."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from random import Random
from typing import Any
from uuid import UUID, uuid4

import simpy

from backend.api.schemas import AlarmEvent
from backend.simulator.camera_iva import CameraIVA
from backend.simulator.engine import Scenario, ScenarioContext
from backend.simulator.sensors.beam import BeamDecision, BeamSensor
from backend.simulator.sensors.pir import PIRSensor


def build_wall_jump(
    settings: Mapping[str, Any],
    now_factory: Callable[[], datetime] | None = None,
    uuid_factory: Callable[[], UUID] = uuid4,
) -> Scenario:
    """Build the configured seismic, beam, PIR and camera sequence."""
    scenario = settings["simulator"]["scenarios"]["wall_jump"]
    devices = scenario["devices"]
    timings = scenario["timings_seconds"]
    beam = BeamSensor.from_settings(dict(settings))
    pir = PIRSensor.from_settings(
        dict(settings),
        Random(int(scenario["random_seed"])),
    )
    camera = CameraIVA(
        line_start=tuple(scenario["camera_line"]["start"]),
        line_end=tuple(scenario["camera_line"]["end"]),
    )
    clock = now_factory or (lambda: datetime.now(timezone.utc))

    def create_event(
        context: ScenarioContext,
        started_at: datetime,
        name: str,
        offset: float,
        source_type: str,
        sia_code: str,
        priority_level: str,
    ) -> AlarmEvent:
        device = devices[name]
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
                "event_status": "ACTIVE",
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
                "wall_jump clock must return a timezone-aware value"
            )
        events = []

        seismic = create_event(
            context,
            started_at,
            "seismic",
            timings["seismic"],
            "PERIMETER_SENSOR",
            "SA",
            "HIGH",
        )
        events.append(seismic)
        context.emit(seismic)

        yield environment.timeout(
            context.delay(timings["beam"] - timings["seismic"])
        )
        if beam.classify(scenario["beam_block_ms"]) is not BeamDecision.ALARM:
            raise RuntimeError("wall_jump beam interruption did not alarm")
        beam_event = create_event(
            context,
            started_at,
            "beam",
            timings["beam"],
            "PERIMETER_SENSOR",
            "BA",
            "CRITICAL",
        )
        events.append(beam_event)
        context.emit(beam_event)

        yield environment.timeout(
            context.delay(timings["pir"] - timings["beam"])
        )
        if not pir.detect(at=started_at + timedelta(seconds=timings['pir'])):
            raise RuntimeError("wall_jump PIR did not detect the intruder")
        pir_event = create_event(
            context,
            started_at,
            "pir",
            timings["pir"],
            "PERIMETER_SENSOR",
            "BA",
            "CRITICAL",
        )
        events.append(pir_event)
        context.emit(pir_event)

        yield environment.timeout(
            context.delay(timings["camera"] - timings["pir"])
        )
        movement = scenario["camera_movement"]
        if not camera.crossed_line(
            tuple(movement["previous"]),
            tuple(movement["current"]),
        ):
            raise RuntimeError(
                "wall_jump movement did not cross the camera line"
            )
        camera_event = create_event(
            context,
            started_at,
            "camera",
            timings["camera"],
            "CAMERA",
            "BA",
            "CRITICAL",
        )
        events.append(camera_event)
        context.emit(camera_event)
        return events

    return run
