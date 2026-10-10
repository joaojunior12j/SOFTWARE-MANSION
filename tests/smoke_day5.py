"""Manual Day 5 smoke test against local Mosquitto and TimescaleDB."""

from time import monotonic

from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.api.schemas import AlarmEvent
from backend.core.event_bus import EventPublisher
from backend.core.settings import load_settings
from tests.test_event_contract import CANONICAL_EVENT


def main() -> None:
    """Publish one MQTT event and assert the live API receives it."""
    settings = load_settings()
    mqtt = settings["mqtt"]
    app = create_app(settings=settings)
    with TestClient(app) as client:
        response = client.get("/api/alarmes/ativos")
        response.raise_for_status()
        with client.websocket_connect("/api/eventos/stream") as socket:
            event = AlarmEvent.model_validate(CANONICAL_EVENT)
            started = monotonic()
            with EventPublisher(
                host=mqtt["host"],
                port=mqtt["port"],
                keepalive=mqtt["keepalive"],
            ) as publisher:
                topic = publisher.publish(event)
            received = socket.receive_json()
            elapsed = monotonic() - started

    if received["event_id"] != CANONICAL_EVENT["event_id"]:
        raise RuntimeError("WebSocket returned a different event")
    if elapsed >= 3.0:
        raise RuntimeError(f"WebSocket delivery exceeded 3s: {elapsed:.3f}s")
    print(
        f"GET alarms={len(response.json())}; topic={topic}; "
        f"websocket_latency={elapsed:.3f}s"
    )


if __name__ == "__main__":
    main()
