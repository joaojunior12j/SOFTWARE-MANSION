"""MQTT publisher wrapper for canonical PSIM events."""

from __future__ import annotations

import argparse
from pathlib import Path
from threading import Event
from typing import Any

import paho.mqtt.client as mqtt

from backend.api.schemas import AlarmEvent
from backend.core.settings import load_settings
from backend.core.topics import topic_for_event


class EventPublisher:
    """Publish validated events with MQTT QoS 1 delivery."""

    def __init__(
        self,
        host: str,
        port: int,
        keepalive: int = 60,
        client: mqtt.Client | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.keepalive = keepalive
        self.client = client or mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="psim-event-publisher",
        )
        self.connected = Event()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        if reason_code.is_failure:
            return
        self.connected.set()

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        self.connected.clear()

    def connect(self, timeout: float = 10.0) -> None:
        """Connect to Mosquitto and wait until the broker acknowledges it."""
        self.client.connect(self.host, self.port, self.keepalive)
        self.client.loop_start()
        if not self.connected.wait(timeout):
            self.client.loop_stop()
            raise TimeoutError("MQTT connection timed out")

    def publish(self, event: AlarmEvent, timeout: float | None = None) -> str:
        """Publish one fixed event payload and return its resolved topic."""
        if not self.connected.is_set():
            raise RuntimeError("publisher is not connected")
        if timeout is not None and timeout <= 0:
            raise ValueError("publish timeout must be positive")
        topic = topic_for_event(event)
        result = self.client.publish(
            topic,
            event.model_dump_json(),
            qos=1,
            retain=False,
        )
        if timeout is None:
            result.wait_for_publish()
        else:
            result.wait_for_publish(timeout=timeout)
            if not result.is_published():
                raise TimeoutError("MQTT publish acknowledgement timed out")
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed with code {result.rc}")
        return topic

    def close(self) -> None:
        """Disconnect cleanly and stop the Paho network loop."""
        self.client.disconnect()
        self.client.loop_stop()

    def __enter__(self) -> "EventPublisher":
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def main() -> None:
    """Publish one event supplied as a JSON file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_file", type=Path)
    args = parser.parse_args()

    event = AlarmEvent.model_validate_json(
        args.event_file.read_text(encoding="utf-8")
    )
    settings = load_settings()["mqtt"]
    with EventPublisher(
        host=settings["host"],
        port=settings["port"],
        keepalive=settings["keepalive"],
    ) as publisher:
        print(publisher.publish(event))


if __name__ == "__main__":
    main()
