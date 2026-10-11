"""Manual Day 7 smoke test for the RF-jammer MQTT sequence."""

import json
from threading import Event, Lock
from time import monotonic

import paho.mqtt.client as mqtt

from backend.api.schemas import AlarmEvent
from backend.core.settings import load_settings
from backend.core.topics import event_subscription_topic
from backend.simulator.cli import main as simulator_main


def main() -> None:
    """Publish and verify the three canonical inputs for rule R01."""
    settings = load_settings()
    mqtt_settings = settings["mqtt"]
    account_id = settings["system"]["account_id"]
    messages = []
    lock = Lock()
    received = Event()
    connected = Event()
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="psim-rf-jammer-smoke",
    )

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            raise RuntimeError(f"MQTT rejected smoke client: {reason_code}")
        client.subscribe(event_subscription_topic(account_id), qos=1)
        connected.set()

    def on_message(client, userdata, message):
        event = AlarmEvent.model_validate(json.loads(message.payload))
        with lock:
            messages.append(event)
            if len(messages) >= 3:
                received.set()

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(
        mqtt_settings["host"],
        mqtt_settings["port"],
        mqtt_settings["keepalive"],
    )
    client.loop_start()
    try:
        if not connected.wait(5.0):
            raise TimeoutError("MQTT smoke subscription timed out")
        started = monotonic()
        simulator_main(
            ["--scenario", "rf_jammer", "--account", account_id]
        )
        if not received.wait(3.0):
            raise TimeoutError(f"received only {len(messages)} MQTT events")
        elapsed = monotonic() - started
    finally:
        client.disconnect()
        client.loop_stop()

    expected_statuses = ["DISCONNECTED", "TIMEOUT_SIA_DC09", "ACTIVE"]
    if len(messages) != 3:
        raise RuntimeError(f"expected 3 events, received {len(messages)}")
    if [event.event_status for event in messages] != expected_statuses:
        raise RuntimeError("rf_jammer MQTT event order is invalid")
    if len({event.zone_partition for event in messages}) != 1:
        raise RuntimeError("rf_jammer events must share one partition")
    print(f"rf_jammer_events=3 mqtt_latency={elapsed:.3f}s")


if __name__ == "__main__":
    main()
