"""Runtime connectivity status consumed by the HMI header."""

from fastapi import APIRouter, Request

from backend.api.schemas import SystemStatus


router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status", response_model=SystemStatus)
async def system_status(request: Request) -> SystemStatus:
    """Return whether the API bridge is currently connected to MQTT."""
    bridge = getattr(request.app.state, "mqtt_bridge", None)
    return SystemStatus(
        mqtt_online=bridge is not None and bridge.connected.is_set()
    )
