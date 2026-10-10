"""MQTT topic builders defined by the Sprint 1 architecture."""

from backend.api.schemas import AlarmEvent


def central_events_topic(account_id: str) -> str:
    """Return the normalized central-event topic for one mansion."""
    return f"mansao/{account_id}/eventos/centrais"


def camera_analytics_topic(account_id: str, camera_id: str) -> str:
    """Return the ONVIF analytics topic for one camera."""
    return f"mansao/{account_id}/eventos/cameras/{camera_id}/analytics"


def simulator_control_topic(account_id: str) -> str:
    """Return the simulator command topic for one mansion."""
    return f"mansao/{account_id}/simulador/controle"


def event_subscription_topic(account_id: str) -> str:
    """Return the wildcard consumed by the persistence service."""
    return f"mansao/{account_id}/eventos/#"


def topic_for_event(event: AlarmEvent) -> str:
    """Route cameras to analytics and other normalized events to centrals."""
    if event.source_type == "CAMERA":
        return camera_analytics_topic(
            event.account_id,
            event.device_hardware_id,
        )
    return central_events_topic(event.account_id)
