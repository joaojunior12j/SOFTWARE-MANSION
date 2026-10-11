"""Tests for the Sprint 1 FastAPI HTTP and WebSocket endpoints."""

import unittest
from uuid import UUID

from fastapi.testclient import TestClient

from backend.api.event_stream import EventStream
from backend.api.main import create_app
from backend.api.schemas import AlarmEvent
from backend.db.alarm_repository import (
    AlarmNotFoundError,
    InvalidAlarmTransitionError,
)
from tests.test_alarm_repository import ALARM_ROW
from tests.test_event_contract import CANONICAL_EVENT


SETTINGS = {
    "system": {"account_id": "1234", "version": "1.0.0"},
    "api": {"cors_origins": ["http://localhost:5173"]},
}


class FakeAlarmRepository:
    """Return a fixed alarm without touching PostgreSQL."""

    def __init__(self) -> None:
        self.acknowledge_error = None

    async def list_active(self):
        return [ALARM_ROW]

    async def acknowledge(self, alarm_id, acknowledged_by):
        if self.acknowledge_error is not None:
            raise self.acknowledge_error
        return {
            **ALARM_ROW,
            "state": "ACKNOWLEDGED",
            "acknowledged_by": acknowledged_by,
            "acknowledged_at": ALARM_ROW["triggered_at"],
        }


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
        self.repository = FakeAlarmRepository()
        self.app = create_app(
            settings=SETTINGS,
            alarm_repository=self.repository,
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
        self.assertIn(
            "/api/alarmes/{alarm_id}/acknowledge",
            schema["paths"],
        )

    def test_acknowledges_alarm(self) -> None:
        operator_id = UUID(int=8)
        with TestClient(self.app) as client:
            response = client.post(
                f"/api/alarmes/{ALARM_ROW['alarm_id']}/acknowledge",
                json={"acknowledged_by": str(operator_id)},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "ACKNOWLEDGED")
        self.assertEqual(
            response.json()["acknowledged_by"],
            str(operator_id),
        )

    def test_acknowledge_returns_not_found(self) -> None:
        self.repository.acknowledge_error = AlarmNotFoundError()
        with TestClient(self.app) as client:
            response = client.post(
                f"/api/alarmes/{ALARM_ROW['alarm_id']}/acknowledge",
                json={"acknowledged_by": str(UUID(int=8))},
            )

        self.assertEqual(response.status_code, 404)

    def test_acknowledge_rejects_invalid_transition(self) -> None:
        self.repository.acknowledge_error = InvalidAlarmTransitionError(
            "already acknowledged"
        )
        with TestClient(self.app) as client:
            response = client.post(
                f"/api/alarmes/{ALARM_ROW['alarm_id']}/acknowledge",
                json={"acknowledged_by": str(UUID(int=8))},
            )

        self.assertEqual(response.status_code, 409)
