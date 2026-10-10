"""Real-time event routes for the supervisory HMI."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


router = APIRouter(prefix="/api/eventos", tags=["eventos"])


@router.websocket("/stream")
async def stream_events(websocket: WebSocket) -> None:
    """Keep a client connected while canonical MQTT events are broadcast."""
    stream = websocket.app.state.event_stream
    await stream.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await stream.disconnect(websocket)
