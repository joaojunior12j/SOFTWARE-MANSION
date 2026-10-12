"""Day 12: classification adapter plus canonical ONVIF/MQTT regression."""

from pathlib import Path

from backend.integrations.onvif_listener import ONVIFCameraConfig
from backend.integrations.onvif_metadata import ONVIFMetadataListener
from tests.smoke_day11 import run as run_line_crossing_smoke


def run() -> None:
    """Decode synthetic metadata and verify the existing real MQTT path."""
    fixture = Path(__file__).parent / "fixtures" / "onvif_object_metadata.xml"
    observations = []
    listener = ONVIFMetadataListener(
        ONVIFCameraConfig("S2D12", "CAMERA-SMOKE-METADATA", "01", 3),
        observations.append,
    )
    if listener.receive(fixture.read_bytes()) != 3:
        raise RuntimeError("classification fixture was not decoded")
    if [item.classes[0].label for item in observations] != [
        "Human", "Vehicle", "Vehicle",
    ]:
        raise RuntimeError("unexpected object classifications")
    # Classifications remain observations. Only the existing line-crossing
    # adapter publishes canonical alarm events to the real Mosquitto broker.
    run_line_crossing_smoke()
    print("metadata_decode=ok canonical_mqtt_regression=ok")


if __name__ == "__main__":
    run()
