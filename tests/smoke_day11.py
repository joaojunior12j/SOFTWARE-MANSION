"""Day 11 smoke test for ONVIF normalization and real MQTT delivery."""

from pathlib import Path
from threading import Event
from types import SimpleNamespace
from uuid import uuid4
from xml.etree import ElementTree

import paho.mqtt.client as mqtt

from backend.api.schemas import AlarmEvent
from backend.core.event_bus import EventPublisher
from backend.core.settings import load_settings
from backend.integrations.onvif_listener import ONVIFCameraConfig
from backend.integrations.onvif_listener import ONVIFLineCrossingListener


FIXTURE = Path(__file__).parent / "fixtures" / "onvif_line_crossed.xml"


class FixturePullPoint:
    """Expose the standard fixture through the onvif-zeep service shape."""

    def create_type(self, name):
        if name != "PullMessages":
            raise RuntimeError(f"unexpected request type: {name}")
        return SimpleNamespace()

    def PullMessages(self, request):
        if request.MessageLimit <= 0:
            raise RuntimeError("invalid ONVIF message limit")
        notification = SimpleNamespace(
            Topic=SimpleNamespace(
                _value_1="tns1:RuleEngine/LineDetector/Crossed"
            ),
            Message=SimpleNamespace(
                _value_1=ElementTree.parse(FIXTURE).getroot()
            ),
        )
        return SimpleNamespace(NotificationMessage=[notification])


def run() -> None:
    """Publish one ONVIF fixture and verify its canonical MQTT payload."""
    settings = load_settings()
    mqtt_settings = settings["mqtt"]
    account_id = "S2D11"
    hardware_id = "CAMERA-SMOKE-ONVIF"
    topic = f"mansao/{account_id}/eventos/cameras/{hardware_id}/analytics"
    received = Event()
    captured = {}
    subscriber = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"psim-day11-smoke-{uuid4()}",
    )

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            return
        client.subscribe(topic, qos=1)

    def on_message(client, userdata, message):
        captured["topic"] = message.topic
        captured["payload"] = message.payload.decode("utf-8")
        received.set()

    subscriber.on_connect = on_connect
    subscriber.on_message = on_message
    subscriber.connect(
        mqtt_settings["host"],
        mqtt_settings["port"],
        mqtt_settings["keepalive"],
    )
    subscriber.loop_start()
    publisher = EventPublisher(
        mqtt_settings["host"],
        mqtt_settings["port"],
        mqtt_settings["keepalive"],
    )

    try:
        publisher.connect()
        listener = ONVIFLineCrossingListener(
            FixturePullPoint(),
            publisher,
            ONVIFCameraConfig(account_id, hardware_id, "01", 3),
        )
        if listener.pull_once() != 1:
            raise RuntimeError("ONVIF fixture was not published")
        if not received.wait(5):
            raise RuntimeError("MQTT did not deliver the ONVIF event")

        event = AlarmEvent.model_validate_json(captured["payload"])
        if captured["topic"] != topic:
            raise RuntimeError(f"unexpected MQTT topic: {captured['topic']}")
        if set(event.model_dump()) != set(AlarmEvent.model_fields):
            raise RuntimeError("ONVIF adapter changed the fixed payload")
        if event.source_type != "CAMERA" or event.sia_code != "BA":
            raise RuntimeError("ONVIF event was normalized incorrectly")
    finally:
        publisher.close()
        subscriber.disconnect()
        subscriber.loop_stop()

    print("onvif_line_crossed=ok mqtt_qos1=ok fixed_payload=ok")


def main() -> None:
    """Run the Day 11 smoke test."""
    run()


if __name__ == "__main__":
    main()
