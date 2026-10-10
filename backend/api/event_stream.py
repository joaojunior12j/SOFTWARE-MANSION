"""Broadcast validated MQTT events to connected FastAPI WebSockets."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket
import paho.mqtt.client as mqtt

from backend.api.schemas import AlarmEvent
from backend.db.consumer import parse_message


LOGGER = logging.getLogger(__name__)


class EventStream:
    """Manage live WebSocket clients without polling."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def connection_count(self) -> int:
        """Return the current number of connected operator clients."""
        return len(self._clients)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register one WebSocket client."""
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected client if it is still registered."""
        async with self._lock:
            self._clients.discard(websocket)

    async def publish(self, event: AlarmEvent) -> None:
        """Send one canonical event to every currently connected client."""
        payload = event.model_dump(mode="json")
        async with self._lock:
            clients = tuple(self._clients)

        failed = []
        for websocket in clients:
            try:
                await websocket.send_json(payload)
            except Exception:
                LOGGER.exception("failed to send event to WebSocket client")
                failed.append(websocket)

        if failed:
            async with self._lock:
                for websocket in failed:
                    self._clients.discard(websocket)


class MQTTEventBridge:
    """Subscribe to canonical MQTT events and forward them to WebSockets."""

    def __init__(
        self,
        host: str,
        port: int,
        keepalive: int,
        topic: str,
        stream: EventStream,
        loop: asyncio.AbstractEventLoop,
        client: mqtt.Client | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.keepalive = keepalive
        self.topic = topic
        self.stream = stream
        self.loop = loop
        self.connected = asyncio.Event()
        self.client = client or mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="psim-api-event-stream",
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        if reason_code.is_failure:
            LOGGER.error("MQTT stream connection rejected: %s", reason_code)
            return
        client.subscribe(self.topic, qos=1)
        self.loop.call_soon_threadsafe(self.connected.set)

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        try:
            event, _ = parse_message(message.payload)
        except Exception:
            LOGGER.exception(
                "discarding invalid stream event on %s",
                message.topic,
            )
            return
        future = asyncio.run_coroutine_threadsafe(
            self.stream.publish(event),
            self.loop,
        )
        future.add_done_callback(self._log_publish_failure)

    @staticmethod
    def _log_publish_failure(future: Any) -> None:
        try:
            future.result()
        except Exception:
            LOGGER.exception("failed to broadcast MQTT event")

    async def start(self, timeout: float = 10.0) -> None:
        """Connect to Mosquitto and wait for the event subscription."""
        self.client.connect(self.host, self.port, self.keepalive)
        self.client.loop_start()
        await asyncio.wait_for(self.connected.wait(), timeout=timeout)

    async def close(self) -> None:
        """Disconnect from Mosquitto and stop its network thread."""
        self.client.disconnect()
        self.client.loop_stop()
