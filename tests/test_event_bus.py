"""Tests for the MQTT event publisher wrapper."""

import unittest

import paho.mqtt.client as mqtt

from backend.api.schemas import AlarmEvent
from backend.core.event_bus import EventPublisher
from tests.test_event_contract import CANONICAL_EVENT


class FakeReasonCode:
    """Small Paho reason-code substitute."""

    def __init__(self, is_failure: bool = False) -> None:
        self.is_failure = is_failure


class FakePublishResult:
    """Capture whether the publisher waited for QoS delivery."""

    def __init__(self, rc: int = mqtt.MQTT_ERR_SUCCESS) -> None:
        self.rc = rc
        self.waited = False

    def wait_for_publish(self) -> None:
        self.waited = True


class FakeMqttClient:
    """Paho client substitute with synchronous callbacks."""

    def __init__(self, connect_failure: bool = False) -> None:
        self.connect_failure = connect_failure
        self.on_connect = None
        self.on_disconnect = None
        self.loop_started = False
        self.loop_stopped = False
        self.disconnected = False
        self.published = None
        self.publish_result = FakePublishResult()

    def connect(self, host: str, port: int, keepalive: int) -> None:
        self.connection = (host, port, keepalive)
        self.on_connect(
            self,
            None,
            None,
            FakeReasonCode(self.connect_failure),
            None,
        )

    def loop_start(self) -> None:
        self.loop_started = True

    def loop_stop(self) -> None:
        self.loop_stopped = True

    def publish(self, topic: str, payload: str, qos: int, retain: bool):
        self.published = (topic, payload, qos, retain)
        return self.publish_result

    def disconnect(self) -> None:
        self.disconnected = True


class EventPublisherTests(unittest.TestCase):
    """Verify connection, validation, routing, and QoS behavior."""

    def setUp(self) -> None:
        self.client = FakeMqttClient()
        self.publisher = EventPublisher(
            host="localhost",
            port=1883,
            client=self.client,
        )
        self.event = AlarmEvent.model_validate(CANONICAL_EVENT)

    def test_connect_publish_and_close(self) -> None:
        self.publisher.connect()
        topic = self.publisher.publish(self.event)
        self.publisher.close()

        self.assertEqual(topic, "mansao/1234/eventos/centrais")
        self.assertEqual(self.client.published[2:], (1, False))
        self.assertTrue(self.client.publish_result.waited)
        self.assertTrue(self.client.disconnected)
        self.assertTrue(self.client.loop_stopped)

    def test_publish_requires_connection(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            self.publisher.publish(self.event)

    def test_connect_failure_times_out(self) -> None:
        client = FakeMqttClient(connect_failure=True)
        publisher = EventPublisher("localhost", 1883, client=client)

        with self.assertRaises(TimeoutError):
            publisher.connect(timeout=0)

        self.assertTrue(client.loop_stopped)

    def test_publish_failure_is_reported(self) -> None:
        self.client.publish_result.rc = mqtt.MQTT_ERR_NO_CONN
        self.publisher.connected.set()

        with self.assertRaisesRegex(RuntimeError, "code"):
            self.publisher.publish(self.event)

    def test_disconnect_callback_clears_state(self) -> None:
        self.publisher.connected.set()

        self.publisher._on_disconnect(
            self.client,
            None,
            None,
            FakeReasonCode(),
            None,
        )

        self.assertFalse(self.publisher.connected.is_set())
