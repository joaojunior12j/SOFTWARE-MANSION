"""Tests for the documented MQTT hierarchy."""

import unittest

from backend.api.schemas import AlarmEvent
from backend.core.topics import (
    camera_analytics_topic,
    central_events_topic,
    event_subscription_topic,
    simulator_control_topic,
    topic_for_event,
)
from tests.test_event_contract import CANONICAL_EVENT


class TopicTests(unittest.TestCase):
    """Protect all MQTT topic names from accidental drift."""

    def test_documented_topics(self) -> None:
        self.assertEqual(
            central_events_topic("1234"),
            "mansao/1234/eventos/centrais",
        )
        self.assertEqual(
            camera_analytics_topic("1234", "CAM-01"),
            "mansao/1234/eventos/cameras/CAM-01/analytics",
        )
        self.assertEqual(
            simulator_control_topic("1234"),
            "mansao/1234/simulador/controle",
        )
        self.assertEqual(
            event_subscription_topic("1234"),
            "mansao/1234/eventos/#",
        )

    def test_routes_camera_to_analytics(self) -> None:
        event = AlarmEvent.model_validate(
            {
                **CANONICAL_EVENT,
                "source_type": "CAMERA",
                "device_hardware_id": "CAM-01",
            }
        )

        self.assertEqual(
            topic_for_event(event),
            "mansao/1234/eventos/cameras/CAM-01/analytics",
        )

    def test_routes_normalized_sensor_to_centrals(self) -> None:
        event = AlarmEvent.model_validate(CANONICAL_EVENT)

        self.assertEqual(
            topic_for_event(event),
            "mansao/1234/eventos/centrais",
        )
