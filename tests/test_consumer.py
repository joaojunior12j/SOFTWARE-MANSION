"""Tests for MQTT payload decoding before persistence."""

import json
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from backend.db.consumer import EventConsumer, parse_message
from tests.test_event_contract import CANONICAL_EVENT


class ConsumerParsingTests(unittest.TestCase):
    """Reject malformed messages before they can reach TimescaleDB."""

    def test_parses_valid_utf8_json(self) -> None:
        event, raw_payload = parse_message(
            json.dumps(CANONICAL_EVENT).encode("utf-8")
        )

        self.assertEqual(event.sia_code, "BA")
        self.assertEqual(raw_payload, CANONICAL_EVENT)

    def test_rejects_json_array(self) -> None:
        with self.assertRaisesRegex(ValueError, "JSON object"):
            parse_message(b"[]")

    def test_rejects_contract_violation(self) -> None:
        payload = {**CANONICAL_EVENT}
        del payload["event_id"]

        with self.assertRaises(ValidationError):
            parse_message(json.dumps(payload).encode("utf-8"))


class FakeLoop:
    """Execute thread-safe callbacks immediately."""

    def call_soon_threadsafe(self, callback) -> None:
        callback()


class FakeClient:
    """Capture subscriptions and lifecycle calls."""

    def __init__(self) -> None:
        self.on_connect = None
        self.on_message = None
        self.subscription = None
        self.disconnected = False
        self.loop_stopped = False

    def subscribe(self, topic: str, qos: int) -> None:
        self.subscription = (topic, qos)

    def disconnect(self) -> None:
        self.disconnected = True

    def loop_stop(self) -> None:
        self.loop_stopped = True


class FakeRepository:
    """Repository substitute used by callback tests."""

    def __init__(self) -> None:
        self.closed = False

    async def save(self, event, raw_payload) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


class FakeReasonCode:
    """Paho reason-code substitute."""

    def __init__(self, is_failure: bool = False) -> None:
        self.is_failure = is_failure

    def __str__(self) -> str:
        return "failure" if self.is_failure else "success"


class FakeFuture:
    """Concurrent future substitute for persistence callbacks."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.callback = None

    def add_done_callback(self, callback) -> None:
        self.callback = callback

    def result(self) -> None:
        if self.error:
            raise self.error


class FakeMessage:
    """Paho message substitute."""

    topic = "mansao/1234/eventos/centrais"

    def __init__(self, payload: bytes) -> None:
        self.payload = payload


class EventConsumerTests(unittest.TestCase):
    """Verify MQTT callbacks bridge safely into async persistence."""

    def setUp(self) -> None:
        self.client = FakeClient()
        self.repository = FakeRepository()
        self.consumer = EventConsumer(
            host="localhost",
            port=1883,
            keepalive=60,
            topic="mansao/1234/eventos/#",
            repository=self.repository,
            loop=FakeLoop(),
            client=self.client,
        )

    def test_successful_connection_subscribes(self) -> None:
        self.consumer._on_connect(
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
        self.assertTrue(self.consumer.connected.is_set())

    def test_rejected_connection_does_not_subscribe(self) -> None:
        with self.assertLogs("backend.db.consumer", level="ERROR"):
            self.consumer._on_connect(
                self.client,
                None,
                None,
                FakeReasonCode(is_failure=True),
                None,
            )

        self.assertIsNone(self.client.subscription)

    def test_valid_message_schedules_persistence(self) -> None:
        future = FakeFuture()

        def schedule(coroutine, loop):
            coroutine.close()
            return future

        payload = json.dumps(CANONICAL_EVENT).encode("utf-8")
        with patch(
            "backend.db.consumer.asyncio.run_coroutine_threadsafe",
            side_effect=schedule,
        ):
            self.consumer._on_message(
                self.client,
                None,
                FakeMessage(payload),
            )

        self.assertIsNotNone(future.callback)
        future.callback(future)

    def test_invalid_message_is_discarded(self) -> None:
        with self.assertLogs("backend.db.consumer", level="ERROR"):
            self.consumer._on_message(
                self.client,
                None,
                FakeMessage(b"not-json"),
            )

    def test_persistence_failure_is_logged(self) -> None:
        future = FakeFuture(RuntimeError("database unavailable"))

        with self.assertLogs("backend.db.consumer", level="ERROR"):
            self.consumer._log_persistence_failure(future)

    def test_close_releases_resources(self) -> None:
        coroutine = self.consumer.close()
        with self.assertRaises(StopIteration):
            coroutine.send(None)

        self.assertTrue(self.client.disconnected)
        self.assertTrue(self.client.loop_stopped)
        self.assertTrue(self.repository.closed)
