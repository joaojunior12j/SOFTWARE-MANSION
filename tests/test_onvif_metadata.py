"""Behavior and boundary tests for ONVIF classification metadata."""

from pathlib import Path
from threading import Event
import unittest
from unittest.mock import patch

from backend.api.schemas import AlarmEvent
from backend.integrations.onvif_listener import ONVIFCameraConfig
from backend.integrations.onvif_metadata import ONVIFMetadataListener
from backend.integrations.onvif_metadata import main, parse_object_metadata


FIXTURE = Path(__file__).parent / "fixtures" / "onvif_object_metadata.xml"
CAMERA = ONVIFCameraConfig("1234", "CAMERA-TEST", "01", 3)


def document(classes='<tt:Type Likelihood="0.95">Human</tt:Type>',
             timestamp="2026-10-12T15:00:00Z", object_id="21"):
    """Make one synthetic observation, varying invalid input boundaries."""
    return (
        '<tt:MetadataStream xmlns:tt="http://www.onvif.org/ver10/schema">'
        '<tt:VideoAnalytics>'
        f'<tt:Frame UtcTime="{timestamp}"><tt:Object ObjectId="{object_id}">'
        f'<tt:Appearance><tt:Class>{classes}</tt:Class></tt:Appearance>'
        '</tt:Object></tt:Frame></tt:VideoAnalytics></tt:MetadataStream>'
    )


class MetadataParserTests(unittest.TestCase):
    """Check supported XML schemas, observation identity and validation."""

    def test_modern_and_legacy_classes_preserve_context(self):
        observations = parse_object_metadata(FIXTURE.read_bytes(), CAMERA)
        self.assertEqual(len(observations), 3)
        self.assertEqual(
            [item.classes[0].label for item in observations],
            ["Human", "Vehicle", "Vehicle"],
        )
        self.assertEqual(observations[1].classes[0].likelihood, 0.93)
        self.assertEqual(observations[2].classes[0].likelihood, 0.9)
        self.assertEqual(observations[0].analytics_source, "analytics-test")
        self.assertEqual(observations[0].object_id, "21")
        self.assertEqual(observations[0].account_id, CAMERA.account_id)
        self.assertEqual(
            observations[0].device_hardware_id, CAMERA.hardware_id,
        )
        self.assertEqual(observations[0].zone_partition, CAMERA.zone_partition)
        self.assertEqual(observations[0].zone_number, CAMERA.zone_number)
        self.assertEqual(
            observations[2].timestamp.isoformat(),
            "2026-10-12T15:00:01+00:00",
        )

    def test_namespace_prefix_is_arbitrary(self):
        xml = document().replace("tt:", "scene:").replace(
            "xmlns:tt", "xmlns:scene",
        )
        self.assertEqual(len(parse_object_metadata(xml, CAMERA)), 1)

    def test_missing_confidence_is_not_fabricated(self):
        observations = parse_object_metadata(
            document('<tt:Type>Human</tt:Type>'), CAMERA,
        )
        self.assertIsNone(observations[0].classes[0].likelihood)

    def test_does_not_choose_a_winner_among_classes(self):
        observations = parse_object_metadata(document(
            '<tt:Type Likelihood="0.5">Human</tt:Type>'
            '<tt:Type Likelihood="0.5">Vehicle</tt:Type>',
        ), CAMERA)
        self.assertEqual(len(observations[0].classes), 2)

    def test_ignores_unknown_or_missing_classes(self):
        for classes in (
            '<tt:Type>Animal</tt:Type>', '<tt:ClassCandidate/>', '',
        ):
            with self.subTest(classes=classes):
                self.assertEqual(
                    parse_object_metadata(document(classes), CAMERA), [],
                )
        xml = document().replace('<tt:Class>', '').replace('</tt:Class>', '')
        self.assertEqual(parse_object_metadata(xml, CAMERA), [])

    def test_rejects_missing_or_ambiguous_identity_and_time(self):
        for xml in (
            document(timestamp=""), document(timestamp="invalid"),
            document(timestamp="2026-10-12T15:00:00"),
            document(object_id=""),
            document().replace('UtcTime="2026-10-12T15:00:00Z"', ''),
            document().replace('ObjectId="21"', ''),
        ):
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                parse_object_metadata(xml, CAMERA)

    def test_rejects_invalid_likelihoods(self):
        for confidence in ("-0.1", "1.1", "NaN", "inf", "invalid", ""):
            with self.subTest(confidence=confidence):
                with self.assertRaises(ValueError):
                    parse_object_metadata(document(
                        f'<tt:Type Likelihood="{confidence}">Human</tt:Type>',
                    ), CAMERA)

    def test_refuses_malformed_wrong_namespace_and_dtd(self):
        for xml in (
            '<broken', '<MetaDataStream/>',
            document().replace(NS_URI, 'urn:vendor'),
            '<!DOCTYPE tt:MetadataStream [<!ENTITY x "Human">]>'
            + document('<tt:Type>&x;</tt:Type>'),
        ):
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                parse_object_metadata(xml, CAMERA)

    def test_refuses_utf16_dtd_and_oversized_document(self):
        xml = '<!DOCTYPE tt:MetadataStream>' + document()
        with self.assertRaisesRegex(ValueError, "DTD"):
            parse_object_metadata(xml.encode('utf-16'), CAMERA)
        with self.assertRaisesRegex(ValueError, "size limit"):
            parse_object_metadata(document(), CAMERA, max_document_bytes=10)
        with self.assertRaises(ValueError):
            parse_object_metadata(document(), CAMERA, max_document_bytes=0)

    def test_classifications_cannot_be_used_as_alarm_events(self):
        observation = parse_object_metadata(document(), CAMERA)[0]
        with self.assertRaises(ValueError):
            AlarmEvent.model_validate(observation.model_dump())


NS_URI = "http://www.onvif.org/ver10/schema"


class MetadataListenerTests(unittest.TestCase):
    """Verify delivery without publication or partial invalid documents."""

    def test_receives_documents_and_obeys_stop(self):
        received = []
        listener = ONVIFMetadataListener(CAMERA, received.append)
        self.assertEqual(listener.run([FIXTURE.read_bytes(), document()]), 4)
        self.assertEqual(len(received), 4)
        stop = Event()
        stop.set()
        self.assertEqual(listener.run([document()], stop), 0)
        self.assertEqual(listener.run([]), 0)

    def test_invalid_document_delivers_no_partial_observations(self):
        received = []
        listener = ONVIFMetadataListener(CAMERA, received.append)
        xml = FIXTURE.read_text(encoding="utf-8").replace(
            '<tt:Likelihood>0.9</tt:Likelihood>',
            '<tt:Likelihood>2</tt:Likelihood>',
        )
        with self.assertRaises(ValueError):
            listener.receive(xml)
        self.assertEqual(received, [])

    def test_callback_failures_propagate(self):
        def failing_callback(observation):
            raise RuntimeError("sink failed")
        listener = ONVIFMetadataListener(CAMERA, failing_callback)
        with self.assertRaisesRegex(RuntimeError, "sink failed"):
            listener.receive(document())

    def test_invalid_size_setting(self):
        with self.assertRaises(ValueError):
            ONVIFMetadataListener(CAMERA, lambda item: None, 0)

    def test_cli_inspects_captured_document(self):
        args = [
            "onvif_metadata", str(FIXTURE), "--account", "1234",
            "--camera-id", "CAMERA-TEST", "--partition", "01", "--zone", "3",
        ]
        settings = {"integrations": {"onvif": {"metadata_max_bytes": 1048576}}}
        with patch("sys.argv", args), patch(
            "backend.integrations.onvif_metadata.load_settings",
            return_value=settings,
        ), patch("builtins.print") as output:
            main()
        self.assertEqual(output.call_count, 3)
