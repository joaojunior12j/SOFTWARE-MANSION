"""Manual Day 6 smoke test for four wall-jump MQTT events."""

import json
from threading import Event, Lock
from time import monotonic

import paho.mqtt.client as mqtt

from backend.api.schemas import AlarmEvent
from backend.core.settings import load_settings
from backend.core.topics import event_subscription_topic
from backend.simulator.cli import main as simulator_main


def main() -> None:
    """Subscribe to MQTT, run the CLI and verify all four fixed payloads."""
    settings = load_settings()
    mqtt_settings = settings["mqtt"]
    account_id = settings["system"]["account_id"]
    messages = []
    lock = Lock()
    received = Event()
    connected = Event()
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="psim-wall-jump-smoke",
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
            if len(messages) >= 4:
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
            ["--scenario", "wall_jump", "--account", account_id]
        )
        if not received.wait(3.0):
            raise TimeoutError(f"received only {len(messages)} MQTT events")
        elapsed = monotonic() - started
    finally:
        client.disconnect()
        client.loop_stop()

    if len(messages) != 4:
        raise RuntimeError(f"expected 4 events, received {len(messages)}")
    if [event.sia_code for event in messages] != ["SA", "BA", "BA", "BA"]:
        raise RuntimeError("wall_jump MQTT event order is invalid")
    print(f"wall_jump_events=4 mqtt_latency={elapsed:.3f}s")


if __name__ == "__main__":
    main()
