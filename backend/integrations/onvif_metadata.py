"""Decode ONVIF scene descriptions without turning classifications into alarms.

Transport adapters must supply complete XML documents, after RTP reassembly.
This module deliberately does not implement RTSP/RTP or a camera subscription.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Literal

from lxml import etree
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.settings import load_settings
from backend.integrations.onvif_listener import ONVIFCameraConfig


NS = {"tt": "http://www.onvif.org/ver10/schema"}
METADATA_TAG = f"{{{NS['tt']}}}MetaDataStream"


class ObjectClass(BaseModel):
    """One supported camera classification; absent confidence stays unknown."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: Literal["Human", "Vehicle"]
    likelihood: float | None = Field(default=None, ge=0, le=1)


class CameraObjectMetadata(BaseModel):
    """Observation contract separate from the canonical AlarmEvent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: datetime
    account_id: str
    device_hardware_id: str
    zone_partition: str
    zone_number: int
    object_id: str = Field(min_length=1)
    analytics_source: str | None = None
    classes: tuple[ObjectClass, ...]

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Reject an ambiguous Frame UtcTime instead of using local time."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Frame UtcTime must include a timezone offset")
        return value


def _classes(element: etree._Element) -> tuple[ObjectClass, ...]:
    candidates = []
    for candidate in element.findall("tt:ClassCandidate", NS):
        candidates.append((
            candidate.findtext("tt:Type", namespaces=NS),
            candidate.findtext("tt:Likelihood", namespaces=NS),
        ))
    for candidate in element.findall("tt:Type", NS):
        candidates.append((candidate.text, candidate.get("Likelihood")))

    result = []
    for label, likelihood in candidates:
        label = (label or "").strip()
        if label not in ("Human", "Vehicle"):
            continue
        result.append(ObjectClass(label=label, likelihood=likelihood))
    return tuple(result)


def parse_object_metadata(
    document: bytes | str,
    camera: ONVIFCameraConfig,
    max_document_bytes: int = 1_048_576,
) -> list[CameraObjectMetadata]:
    """Parse complete tt:MetaDataStream XML with legacy or modern classes.

    Unsupported classes are ignored. Invalid supported observations reject
    the document before callbacks. DTDs/entities are refused. Images, face
    attributes, license plates and vendor extensions are not retained.
    """
    if max_document_bytes <= 0:
        raise ValueError("max_document_bytes must be positive")
    data = document.encode("utf-8") if isinstance(document, str) else document
    if len(data) > max_document_bytes:
        raise ValueError("ONVIF metadata document exceeds the size limit")
    parser = etree.XMLParser(
        resolve_entities=False, load_dtd=False, no_network=True,
    )
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as error:
        raise ValueError("invalid ONVIF metadata XML") from error
    if root.getroottree().docinfo.doctype:
        raise ValueError("ONVIF metadata DTDs are not supported")
    if root.tag != METADATA_TAG:
        raise ValueError("expected ONVIF tt:MetaDataStream")

    observations = []
    for frame in root.findall("tt:VideoAnalytics/tt:Frame", NS):
        for obj in frame.findall("tt:Object", NS):
            descriptor = obj.find("tt:Appearance/tt:Class", NS)
            if descriptor is None:
                continue
            classes = _classes(descriptor)
            if not classes:
                continue
            observations.append(CameraObjectMetadata(
                timestamp=frame.get("UtcTime"),
                account_id=camera.account_id,
                device_hardware_id=camera.hardware_id,
                zone_partition=camera.zone_partition,
                zone_number=camera.zone_number,
                object_id=obj.get("ObjectId"),
                analytics_source=frame.get("Source"),
                classes=classes,
            ))
    return observations


class ONVIFMetadataListener:
    """Deliver observations from an injected source of complete XML."""

    def __init__(
        self,
        camera: ONVIFCameraConfig,
        on_metadata: Callable[[CameraObjectMetadata], None],
        max_document_bytes: int = 1_048_576,
    ) -> None:
        if max_document_bytes <= 0:
            raise ValueError("max_document_bytes must be positive")
        self.camera = camera
        self.on_metadata = on_metadata
        self.max_document_bytes = max_document_bytes

    def receive(self, document: bytes | str) -> int:
        """Validate the document, then deliver supported observations."""
        observations = parse_object_metadata(
            document, self.camera, self.max_document_bytes,
        )
        for observation in observations:
            self.on_metadata(observation)
        return len(observations)

    def run(
        self,
        documents: Iterable[bytes | str],
        stop_event: Event | None = None,
    ) -> int:
        """Consume documents until source exhaustion or a stop request.

        The transport remains responsible for read timeouts and cancellation of
        blocked reads. Parsing/callback errors propagate to its supervisor.
        """
        count = 0
        for document in documents:
            if stop_event is not None and stop_event.is_set():
                break
            count += self.receive(document)
        return count


def main() -> None:
    """Inspect a local metadata document without camera credentials."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata_file", type=Path)
    parser.add_argument("--account", required=True)
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--partition", required=True)
    parser.add_argument("--zone", required=True, type=int)
    args = parser.parse_args()
    limit = load_settings()["integrations"]["onvif"]["metadata_max_bytes"]
    listener = ONVIFMetadataListener(
        ONVIFCameraConfig(
            args.account, args.camera_id, args.partition, args.zone,
        ),
        lambda observation: print(observation.model_dump_json()),
        max_document_bytes=limit,
    )
    with args.metadata_file.open("rb") as stream:
        listener.receive(stream.read(limit + 1))


if __name__ == "__main__":
    main()
