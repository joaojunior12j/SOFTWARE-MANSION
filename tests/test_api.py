"""Tests for the Sprint 1 FastAPI HTTP and WebSocket endpoints."""

import unittest

from fastapi.testclient import TestClient

from backend.api.event_stream import EventStream
from backend.api.main import create_app
from backend.api.schemas import AlarmEvent
from tests.test_alarm_repository import ALARM_ROW
from tests.test_event_contract import CANONICAL_EVENT


SETTINGS = {
    "system": {"account_id": "1234", "version": "1.0.0"},
    "api": {"cors_origins": ["http://localhost:5173"]},
}


class FakeAlarmRepository:
    """Return a fixed alarm without touching PostgreSQL."""

    async def list_active(self):
        return [ALARM_ROW]


class ImmediateEventStream(EventStream):
    """Send one canonical event as soon as a test client connects."""

    async def connect(self, websocket) -> None:
        await super().connect(websocket)
        event = AlarmEvent.model_validate(CANONICAL_EVENT)
        await websocket.send_json(event.model_dump(mode="json"))


class APITests(unittest.TestCase):
    """Verify the public endpoint contracts used by the future HMI."""

    def setUp(self) -> None:
        self.stream = ImmediateEventStream()
        self.app = create_app(
            settings=SETTINGS,
            alarm_repository=FakeAlarmRepository(),
            event_stream=self.stream,
            start_services=False,
        )

    def test_get_active_alarms(self) -> None:
        with TestClient(self.app) as client:
            response = client.get("/api/alarmes/ativos")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["priority_level"], "CRITICAL")
        self.assertEqual(response.json()[0]["state"], "UNACKNOWLEDGED")

    def test_websocket_streams_canonical_event(self) -> None:
        with TestClient(self.app) as client:
            with client.websocket_connect("/api/eventos/stream") as socket:
                payload = socket.receive_json()

        self.assertEqual(payload["event_id"], CANONICAL_EVENT["event_id"])
        self.assertEqual(payload["source_type"], "PERIMETER_SENSOR")
        self.assertEqual(self.stream.connection_count, 0)

    def test_openapi_documents_alarm_route(self) -> None:
        with TestClient(self.app) as client:
            schema = client.get("/openapi.json").json()

        self.assertIn("/api/alarmes/ativos", schema["paths"])
