"""Sprint 1 correlation rules R01 Jammer and R02 Multi-sensor."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import timedelta
from itertools import product
from typing import Any

from backend.api.schemas import AlarmEvent
from backend.core.correlation_engine import CorrelationRule


class JammerRule:
    """Match camera, SIA and PIR disruption within fifteen seconds."""

    rule_id = "R01_JAMMER"
    confidence_score = 0.95
    title = "JAMMER RF — ATAQUE ALTAMENTE PROVÁVEL"
    description = "Câmera offline, timeout SIA DC-09 e PIR ativo."
    priority_level = "CRITICAL"

    def __init__(self, window_seconds: float = 15) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.window_seconds = float(window_seconds)

    def match(
        self,
        events: Sequence[AlarmEvent],
    ) -> Sequence[AlarmEvent] | None:
        """Return the most recent valid R01 event combination."""
        available = [event for event in events if event.correlation_id is None]
        cameras = [
            event
            for event in available
            if event.source_type == "CAMERA"
            and event.event_status == "DISCONNECTED"
        ]
        panels = [
            event
            for event in available
            if event.source_type == "ALARM_PANEL"
            and event.event_status == "TIMEOUT_SIA_DC09"
        ]
        sensors = [
            event
            for event in available
            if event.source_type == "PERIMETER_SENSOR"
            and event.sia_code == "BA"
            and event.event_status == "ACTIVE"
        ]
        valid = []
        limit = timedelta(seconds=self.window_seconds)
        for candidate in product(cameras, panels, sensors):
            timestamps = [event.timestamp for event in candidate]
            if max(timestamps) - min(timestamps) <= limit:
                valid.append(
                    tuple(
                        sorted(candidate, key=lambda item: item.timestamp)
                    )
                )
        if not valid:
            return None
        return max(valid, key=lambda candidate: candidate[-1].timestamp)


class MultiSensorRule:
    """Match three distinct intrusion sensors inside a sixty-second window."""

    rule_id = "R02_MULTI_SENSOR"
    confidence_score = 0.98
    title = "INTRUSÃO CONFIRMADA — MÚLTIPLOS SENSORES"
    description = "Três ou mais dispositivos confirmaram a intrusão."
    priority_level = "CRITICAL"

    def __init__(self, window_seconds: float = 60) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.window_seconds = float(window_seconds)

    def match(
        self,
        events: Sequence[AlarmEvent],
    ) -> Sequence[AlarmEvent] | None:
        """Return the latest event from each distinct eligible device."""
        eligible = [
            event
            for event in events
            if event.correlation_id is None and event.sia_code in {"BA", "SA"}
        ]
        if not eligible:
            return None
        latest_timestamp = max(event.timestamp for event in eligible)
        cutoff = latest_timestamp - timedelta(seconds=self.window_seconds)
        latest_by_device = {}
        for event in eligible:
            if event.timestamp < cutoff:
                continue
            previous = latest_by_device.get(event.device_hardware_id)
            if previous is None or event.timestamp > previous.timestamp:
                latest_by_device[event.device_hardware_id] = event
        if len(latest_by_device) < 3:
            return None
        return tuple(
            sorted(
                latest_by_device.values(),
                key=lambda item: item.timestamp,
            )
        )


def build_rules(settings: Mapping[str, Any]) -> tuple[CorrelationRule, ...]:
    """Build the configured Sprint 1 rules in specificity order."""
    correlation = settings["correlation_engine"]
    return (
        JammerRule(correlation["jammer_window_seconds"]),
        MultiSensorRule(correlation["window_seconds"]),
    )
