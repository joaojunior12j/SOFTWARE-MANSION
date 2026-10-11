"""MQTT consumer that validates and persists every canonical event."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from backend.api.schemas import AlarmEvent
from backend.core.correlation_engine import CorrelationEngine
from backend.core.settings import load_settings
from backend.core.topics import event_subscription_topic
from backend.db.correlation_repository import CorrelationRepository
from backend.db.repository import EventRepository


LOGGER = logging.getLogger(__name__)


def parse_message(payload: bytes) -> tuple[AlarmEvent, dict[str, Any]]:
    """Decode UTF-8 JSON and enforce the fixed event contract."""
    raw_payload = json.loads(payload.decode("utf-8"))
    if not isinstance(raw_payload, dict):
        raise ValueError("event payload must be a JSON object")
    return AlarmEvent.model_validate(raw_payload), raw_payload


class EventConsumer:
    """Bridge the Paho network thread to the async database repository."""

    def __init__(
        self,
        host: str,
        port: int,
        keepalive: int,
        topic: str,
        repository: EventRepository,
        loop: asyncio.AbstractEventLoop,
        client: mqtt.Client | None = None,
        correlation_engine: CorrelationEngine | None = None,
        correlation_repository: CorrelationRepository | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.keepalive = keepalive
        self.topic = topic
        self.repository = repository
        self.correlation_engine = correlation_engine
        self.correlation_repository = correlation_repository
        self.loop = loop
        self.client = client or mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="psim-db-consumer",
        )
        self.connected = asyncio.Event()
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
            LOGGER.error("MQTT connection rejected: %s", reason_code)
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
            event, raw_payload = parse_message(message.payload)
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValidationError,
            ValueError,
        ):
            LOGGER.exception("discarding invalid event on %s", message.topic)
            return

        future = asyncio.run_coroutine_threadsafe(
            self._persist_and_correlate(event, raw_payload),
            self.loop,
        )
        future.add_done_callback(self._log_persistence_failure)

    @staticmethod
    def _log_persistence_failure(future: Any) -> None:
        try:
            future.result()
        except Exception:
            LOGGER.exception("failed to persist or correlate MQTT event")

    async def _persist_and_correlate(
        self,
        event: AlarmEvent,
        raw_payload: dict[str, Any],
    ) -> None:
        """Persist an event before evaluating and storing correlations."""
        await self.repository.save(event, raw_payload)
        if self.correlation_engine is None:
            return
        if self.correlation_repository is None:
            raise RuntimeError("correlation_repository is required")
        for result in self.correlation_engine.process(event):
            await self.correlation_repository.save(result)

    async def start(self, timeout: float = 10.0) -> None:
        """Connect, start the network loop, and wait for the subscription."""
        self.client.connect(self.host, self.port, self.keepalive)
        self.client.loop_start()
        await asyncio.wait_for(self.connected.wait(), timeout=timeout)

    async def close(self) -> None:
        """Disconnect MQTT and close the database pool."""
        self.client.disconnect()
        self.client.loop_stop()
        if self.correlation_repository is not None:
            await self.correlation_repository.close()
        await self.repository.close()


async def run() -> None:
    """Run the database consumer until interrupted."""
    settings = load_settings()
    mqtt_settings = settings["mqtt"]
    account_id = settings["system"]["account_id"]
    repository = EventRepository(settings["database"]["url"])
    correlation_engine = CorrelationEngine(
        settings["correlation_engine"]["window_seconds"]
    )
    correlation_repository = CorrelationRepository(engine=repository.engine)
    consumer = EventConsumer(
        host=mqtt_settings["host"],
        port=mqtt_settings["port"],
        keepalive=mqtt_settings["keepalive"],
        topic=event_subscription_topic(account_id),
        repository=repository,
        loop=asyncio.get_running_loop(),
        correlation_engine=correlation_engine,
        correlation_repository=correlation_repository,
    )
    await consumer.start()
    LOGGER.info("consuming %s", consumer.topic)
    try:
        await asyncio.Event().wait()
    finally:
        await consumer.close()


def main() -> None:
    """Configure logging and start the asynchronous consumer."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
