"""Discover an ONVIF Media1 metadata profile and supervise its RTSP stream."""

import argparse
import logging
import os
from threading import Event

from backend.core.settings import load_settings
from backend.integrations.onvif_listener import ONVIFCameraConfig, _read
from backend.integrations.onvif_metadata import parse_object_metadata
from backend.integrations.onvif_rtsp import RTSPError, RTSPMetadataSource
from backend.integrations.onvif_rtsp import validate_uri


LOGGER = logging.getLogger(__name__)


def discover_metadata_uri(media, profile_token=None):
    """Select an existing analytics metadata profile without altering it."""
    profiles = media.GetProfiles()
    selected = None
    for profile in profiles:
        metadata = _read(profile, "MetadataConfiguration")
        if metadata is None or not _read(metadata, "Analytics", False):
            continue
        token = _read(profile, "token")
        if token and (profile_token is None or token == profile_token):
            selected = token
            break
    if selected is None:
        raise RTSPError("no enabled analytics metadata Media1 profile")
    result = media.GetStreamUri({
        "StreamSetup": {
            "Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"},
        },
        "ProfileToken": selected,
    })
    uri = _read(result, "Uri")
    if not isinstance(uri, str):
        raise RTSPError("missing ONVIF metadata stream URI")
    validate_uri(uri)
    return uri


def camera_stream_uri(host, port, username, password, timeout,
                      profile_token=None):
    """Discover via onvif-zeep with bounded SOAP operations and safe errors."""
    from onvif import ONVIFCamera
    from zeep.transports import Transport

    transport = Transport(timeout=timeout, operation_timeout=timeout)
    try:
        camera = ONVIFCamera(
            host, port, username, password, transport=transport,
        )
        return discover_metadata_uri(
            camera.create_media_service(), profile_token,
        )
    except Exception:
        # SOAP exceptions can contain endpoints and sensitive server responses.
        raise RTSPError("ONVIF metadata discovery failed") from None
    finally:
        transport.session.close()


class MetadataSinkError(Exception):
    """A callback failure stops delivery to prevent replay."""


def run_metadata_stream(source_factory, camera, on_metadata, stop,
                        max_bytes, reconnect_initial=1, reconnect_max=30):
    """Reconnect on transport failures with cancellable exponential backoff.

    Parsing errors discard a complete document. Callback failures terminate the
    supervisor. No network exception, endpoint or credential is logged.
    """
    if (max_bytes <= 0 or reconnect_initial <= 0
            or reconnect_max < reconnect_initial):
        raise ValueError("invalid stream supervisor limits")
    delay = reconnect_initial
    delivered = 0
    while not stop.is_set():
        try:
            with source_factory() as source:
                for document in source.documents(stop):
                    if stop.is_set():
                        break
                    try:
                        observations = parse_object_metadata(
                            document, camera, max_bytes,
                        )
                    except ValueError:
                        LOGGER.warning("Invalid ONVIF metadata dropped")
                        continue
                    for observation in observations:
                        try:
                            on_metadata(observation)
                        except Exception:
                            raise MetadataSinkError(
                                "ONVIF metadata callback failed",
                            ) from None
                        delivered += 1
                    delay = reconnect_initial
        except (OSError, EOFError, RTSPError, ValueError):
            if not stop.is_set():
                LOGGER.warning("Metadata stream unavailable; reconnecting")
        if not stop.is_set():
            stop.wait(delay)
            delay = min(delay * 2, reconnect_max)
    return delivered


def main():
    """Use local environment credentials and print observations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--partition", required=True)
    parser.add_argument("--zone", required=True, type=int)
    parser.add_argument("--profile-token")
    args = parser.parse_args()
    settings = load_settings()["integrations"]["onvif"]
    names = (
        "ONVIF_CAMERA_HOST", "ONVIF_CAMERA_USERNAME", "ONVIF_CAMERA_PASSWORD",
    )
    if not all(os.getenv(name) for name in names):
        parser.error("set local ONVIF camera host, username and password envs")
    host, username, password = (os.environ[name] for name in names)
    port = int(os.getenv("ONVIF_CAMERA_PORT", "80"))
    camera = ONVIFCameraConfig(
        args.account, args.camera_id, args.partition, args.zone,
    )

    def source_factory():
        uri = camera_stream_uri(
            host, port, username, password,
            settings["stream_timeout_seconds"], args.profile_token,
        )
        return RTSPMetadataSource(
            uri, username, password,
            timeout=settings["stream_timeout_seconds"],
            max_bytes=settings["metadata_max_bytes"],
            keepalive=settings["stream_keepalive_seconds"],
        )

    stop = Event()
    try:
        run_metadata_stream(
            source_factory, camera,
            lambda observation: print(observation.model_dump_json()), stop,
            settings["metadata_max_bytes"],
            settings["reconnect_initial_seconds"],
            settings["reconnect_max_seconds"],
        )
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
