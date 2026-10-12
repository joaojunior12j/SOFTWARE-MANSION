"""Tests for ONVIF Profile T line-crossing normalization."""

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from xml.etree import ElementTree

from backend.integrations.onvif_listener import ONVIFCameraConfig
from backend.integrations.onvif_listener import ONVIFLineCrossingListener
from backend.integrations.onvif_listener import translate_line_crossing


FIXTURE = Path(__file__).parent / "fixtures" / "onvif_line_crossed.xml"
CAMERA = ONVIFCameraConfig("1234", "CAMERA-MURO-NORTE", "01", 3)


def notification(topic="tns1:RuleEngine/LineDetector/Crossed", message=None):
    """Build the zeep-compatible notification shape used by the adapter."""
    element = (
        ElementTree.parse(FIXTURE).getroot()
        if message is None
        else message
    )
    return SimpleNamespace(
        Topic=SimpleNamespace(_value_1=topic),
        Message=SimpleNamespace(_value_1=element),
    )


class FakePullPoint:
    """Return one deterministic ONVIF notification batch."""

    def __init__(self, messages) -> None:
        self.messages = messages
        self.request = None

    def create_type(self, name):
        self.request_type = name
        return SimpleNamespace()

    def PullMessages(self, request):
        self.request = request
        return SimpleNamespace(NotificationMessage=self.messages)


class FakePublisher:
    """Capture canonical events without connecting to MQTT."""

    def __init__(self) -> None:
        self.events = []

    def publish(self, event):
        self.events.append(event)
        return "test/topic"


class ONVIFTranslatorTests(unittest.TestCase):
    """Verify strict topic filtering and fixed-payload mapping."""

    def test_translates_line_crossing_to_canonical_event(self) -> None:
        event = translate_line_crossing(notification(), CAMERA)

        self.assertIsNotNone(event)
        self.assertEqual(event.source_type, "CAMERA")
        self.assertEqual(event.device_hardware_id, "CAMERA-MURO-NORTE")
        self.assertEqual(event.sia_code, "BA")
        self.assertEqual(event.event_status, "ACTIVE")
        self.assertEqual(event.priority_level, "CRITICAL")
        self.assertIsNone(event.correlation_id)
        self.assertEqual(
            event.timestamp.isoformat(),
            "2026-10-12T15:00:00+00:00",
        )

    def test_ignores_topics_outside_line_detector(self) -> None:
        event = translate_line_crossing(
            notification("tns1:VideoSource/MotionAlarm"),
            CAMERA,
        )

        self.assertIsNone(event)

    def test_rejects_line_event_without_utc_time(self) -> None:
        message = ElementTree.fromstring(
            '<Message xmlns="http://www.onvif.org/ver10/schema" />'
        )

        with self.assertRaisesRegex(ValueError, "UtcTime"):
            translate_line_crossing(notification(message=message), CAMERA)

    def test_rejects_invalid_camera_metadata(self) -> None:
        with self.assertRaises(ValueError):
            ONVIFCameraConfig("1234", "", "01", 3)
        with self.assertRaises(ValueError):
            ONVIFCameraConfig("1234", "CAM-1", "01", -1)


class ONVIFListenerTests(unittest.TestCase):
    """Verify PullPoint request and MQTT handoff behavior."""

    def test_pulls_batch_and_publishes_only_supported_topic(self) -> None:
        pullpoint = FakePullPoint(
            [notification(), notification("tns1:VideoSource/MotionAlarm")]
        )
        publisher = FakePublisher()
        listener = ONVIFLineCrossingListener(
            pullpoint,
            publisher,
            CAMERA,
            timeout_seconds=7,
            message_limit=25,
        )

        published = listener.pull_once()

        self.assertEqual(published, 1)
        self.assertEqual(len(publisher.events), 1)
        self.assertEqual(pullpoint.request_type, "PullMessages")
        self.assertEqual(pullpoint.request.Timeout, timedelta(seconds=7))
        self.assertEqual(pullpoint.request.MessageLimit, 25)

    def test_accepts_single_notification_and_empty_batch(self) -> None:
        publisher = FakePublisher()
        single = ONVIFLineCrossingListener(
            FakePullPoint(notification()), publisher, CAMERA
        )
        empty = ONVIFLineCrossingListener(
            FakePullPoint(None), publisher, CAMERA
        )

        self.assertEqual(single.pull_once(), 1)
        self.assertEqual(empty.pull_once(), 0)

    def test_rejects_invalid_pull_settings(self) -> None:
        with self.assertRaises(ValueError):
            ONVIFLineCrossingListener(
                FakePullPoint([]), FakePublisher(), CAMERA, 0, 10
            )
