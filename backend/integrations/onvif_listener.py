"""ONVIF Profile T PullPoint listener for line-crossing analytics."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
import os
from threading import Event
from typing import Any
from uuid import uuid4

from backend.api.schemas import AlarmEvent
from backend.core.event_bus import EventPublisher
from backend.core.settings import load_settings


LINE_CROSSED_TOPIC = "RuleEngine/LineDetector/Crossed"


@dataclass(frozen=True)
class ONVIFCameraConfig:
    """Non-secret metadata required to normalize one physical camera."""

    account_id: str
    hardware_id: str
    zone_partition: str
    zone_number: int

    def __post_init__(self) -> None:
        if not all(
            (self.account_id, self.hardware_id, self.zone_partition)
        ):
            raise ValueError("ONVIF camera metadata cannot be empty")
        if self.zone_number < 0:
            raise ValueError("zone_number cannot be negative")


def _read(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _topic_text(notification: Any) -> str:
    topic = _read(notification, "Topic")
    topic_value = _read(topic, "_value_1", topic)
    return "" if topic_value is None else str(topic_value).strip()


def _message_element(notification: Any) -> Any:
    message = _read(notification, "Message")
    return _read(message, "_value_1", message)


def _utc_time(notification: Any) -> str:
    message = _message_element(notification)
    attributes = getattr(message, "attrib", {})
    timestamp = attributes.get("UtcTime") or attributes.get("UTCtime")
    if not timestamp:
        raise ValueError("ONVIF notification is missing Message UtcTime")
    return str(timestamp)


def translate_line_crossing(
    notification: Any,
    camera: ONVIFCameraConfig,
) -> AlarmEvent | None:
    """Translate one standard line-crossing notification to the fixed JSON."""
    if not _topic_text(notification).endswith(LINE_CROSSED_TOPIC):
        return None
    return AlarmEvent(
        event_id=uuid4(),
        timestamp=_utc_time(notification),
        account_id=camera.account_id,
        source_type="CAMERA",
        device_hardware_id=camera.hardware_id,
        zone_partition=camera.zone_partition,
        zone_number=camera.zone_number,
        sia_code="BA",
        event_status="ACTIVE",
        priority_level="CRITICAL",
        correlation_id=None,
    )


class ONVIFLineCrossingListener:
    """Pull ONVIF notifications and publish supported events to MQTT."""

    def __init__(
        self,
        pullpoint: Any,
        publisher: EventPublisher,
        camera: ONVIFCameraConfig,
        timeout_seconds: int = 5,
        message_limit: int = 10,
    ) -> None:
        if timeout_seconds <= 0 or message_limit <= 0:
            raise ValueError(
                "PullPoint timeout and message limit must be positive"
            )
        self.pullpoint = pullpoint
        self.publisher = publisher
        self.camera = camera
        self.timeout_seconds = timeout_seconds
        self.message_limit = message_limit

    def pull_once(self) -> int:
        """Pull one batch and return the number of canonical events sent."""
        request = self.pullpoint.create_type("PullMessages")
        request.Timeout = timedelta(seconds=self.timeout_seconds)
        request.MessageLimit = self.message_limit
        response = self.pullpoint.PullMessages(request)
        notifications = _read(response, "NotificationMessage", []) or []
        if not isinstance(notifications, (list, tuple)):
            notifications = [notifications]

        published = 0
        for notification in notifications:
            event = translate_line_crossing(notification, self.camera)
            if event is not None:
                self.publisher.publish(event)
                published += 1
        return published

    def run_forever(self, stop_event: Event | None = None) -> None:
        """Keep polling until interrupted or the optional event is set."""
        stop = stop_event or Event()
        while not stop.is_set():
            self.pull_once()


def create_pullpoint(
    host: str,
    port: int,
    username: str,
    password: str,
) -> Any:
    """Create the onvif-zeep PullPoint service lazily."""
    from onvif import ONVIFCamera

    camera = ONVIFCamera(host, port, username, password)
    return camera.create_pullpoint_service()


def main() -> None:
    """Run a physical-camera listener without exposing its password in CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--password-env",
        default="ONVIF_CAMERA_PASSWORD",
        help="environment variable containing the camera password",
    )
    parser.add_argument("--account", required=True)
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--partition", required=True)
    parser.add_argument("--zone", required=True, type=int)
    args = parser.parse_args()

    settings = load_settings()
    password = os.getenv(args.password_env)
    if not password:
        parser.error(f"environment variable {args.password_env} is not set")

    onvif_settings = settings["integrations"]["onvif"]
    mqtt_settings = settings["mqtt"]
    publisher = EventPublisher(
        host=mqtt_settings["host"],
        port=mqtt_settings["port"],
        keepalive=mqtt_settings["keepalive"],
    )
    listener = ONVIFLineCrossingListener(
        pullpoint=create_pullpoint(
            args.host,
            args.port,
            args.username,
            password,
        ),
        publisher=publisher,
        camera=ONVIFCameraConfig(
            account_id=args.account,
            hardware_id=args.camera_id,
            zone_partition=args.partition,
            zone_number=args.zone,
        ),
        timeout_seconds=onvif_settings["pull_timeout_seconds"],
        message_limit=onvif_settings["message_limit"],
    )

    publisher.connect()
    try:
        listener.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        publisher.close()


if __name__ == "__main__":
    main()
