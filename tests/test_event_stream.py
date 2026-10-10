"""Tests for WebSocket fan-out and the MQTT-to-API bridge."""

import asyncio
import json
import unittest
from unittest.mock import patch

from backend.api.event_stream import EventStream, MQTTEventBridge
from backend.api.schemas import AlarmEvent
from tests.test_consumer import (
    FakeClient,
    FakeFuture,
    FakeLoop,
    FakeMessage,
    FakeReasonCode,
)
from tests.test_event_contract import CANONICAL_EVENT


class FakeWebSocket:
    """Capture acceptance and JSON messages from EventStream."""

    def __init__(self, fail: bool = False) -> None:
        self.accepted = False
        self.messages = []
        self.fail = fail

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload) -> None:
        if self.fail:
            raise RuntimeError("closed")
        self.messages.append(payload)


class EventStreamTests(unittest.IsolatedAsyncioTestCase):
    """Verify live fan-out and cleanup of disconnected clients."""

    async def test_publishes_to_connected_clients(self) -> None:
        stream = EventStream()
        socket = FakeWebSocket()
        event = AlarmEvent.model_validate(CANONICAL_EVENT)

        await stream.connect(socket)
        await stream.publish(event)

        self.assertTrue(socket.accepted)
        self.assertEqual(socket.messages[0]["sia_code"], "BA")
        self.assertEqual(stream.connection_count, 1)
        await stream.disconnect(socket)
        self.assertEqual(stream.connection_count, 0)

    async def test_removes_client_when_delivery_fails(self) -> None:
        stream = EventStream()
        socket = FakeWebSocket(fail=True)
        await stream.connect(socket)

        with self.assertLogs("backend.api.event_stream", level="ERROR"):
            await stream.publish(AlarmEvent.model_validate(CANONICAL_EVENT))

        self.assertEqual(stream.connection_count, 0)


class MQTTEventBridgeTests(unittest.TestCase):
    """Verify MQTT callbacks subscribe and schedule WebSocket fan-out."""

    def setUp(self) -> None:
        self.client = FakeClient()
        self.stream = EventStream()
        self.bridge = MQTTEventBridge(
            host="localhost",
            port=1883,
            keepalive=60,
            topic="mansao/1234/eventos/#",
            stream=self.stream,
            loop=FakeLoop(),
            client=self.client,
        )

    def test_successful_connection_subscribes(self) -> None:
        self.bridge._on_connect(
            self.client,
            None,
            None,
            FakeReasonCode(),
            None,
        )

        self.assertEqual(
            self.client.subscription,
            ("mansao/1234/eventos/#", 1),
        )

    def test_valid_message_schedules_broadcast(self) -> None:
        future = FakeFuture()

        def schedule(coroutine, loop):
            coroutine.close()
            return future

        message = FakeMessage(json.dumps(CANONICAL_EVENT).encode("utf-8"))
        with patch(
            "backend.api.event_stream.asyncio.run_coroutine_threadsafe",
            side_effect=schedule,
        ):
            self.bridge._on_message(self.client, None, message)

        self.assertIsNotNone(future.callback)

    def test_invalid_message_is_discarded(self) -> None:
        with self.assertLogs("backend.api.event_stream", level="ERROR"):
            self.bridge._on_message(
                self.client,
                None,
                FakeMessage(b"invalid"),
            )

    def test_close_stops_mqtt_client(self) -> None:
        asyncio.run(self.bridge.close())

        self.assertTrue(self.client.disconnected)
        self.assertTrue(self.client.loop_stopped)
