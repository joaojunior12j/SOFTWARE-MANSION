"""Local SIA-DCS TCP receiver: validate, normalize, publish, then ACK."""

import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
import logging
import os
import re
import time
from uuid import NAMESPACE_URL, uuid4, uuid5

import paho.mqtt.client as mqtt

from backend.api.schemas import AlarmEvent
from backend.core.event_bus import EventPublisher
from backend.core.settings import load_settings
from backend.integrations.sia_dc09 import (
    SIAAccount, SIAMessage, SIAProtocolError, acknowledge, parse_message,
)
from backend.integrations.sia_supervision import supervisor_from_settings


LOGGER = logging.getLogger(__name__)
EVENT = re.compile(
    r'#(?P<account>[0-9A-Fa-f]{1,16})\|N'
    r'(?:ri(?P<partition>[0-9]{1,5})/)?'
    r'(?P<code>BA|BR|TA|TR|RP)(?P<zone>[0-9]{1,3})',
)
EVENT_POLICY = {
    'BA': ('ACTIVE', 'CRITICAL'), 'BR': ('RESTORED', 'LOW'),
    'TA': ('TAMPER', 'HIGH'), 'TR': ('RESTORED', 'LOW'),
    'RP': ('ACTIVE', 'LOW'),
}


def translate_message(message: SIAMessage, account: SIAAccount,
                      received_at: datetime) -> AlarmEvent | None:
    """Translate supported event codes; NULL is control, never a fake RP."""
    if message.token == 'NULL':
        return None
    if message.token != 'SIA-DCS':
        raise SIAProtocolError('unsupported inbound control message')
    match = EVENT.fullmatch(message.data)
    if not match or match['account'] != message.account:
        raise SIAProtocolError('unsupported SIA event or account mismatch')
    status, priority = EVENT_POLICY[match['code']]
    event_id = uuid4()
    if message.timestamp is not None:
        identity = (message.account, message.sequence,
                    message.timestamp.isoformat(), message.data)
        event_id = uuid5(NAMESPACE_URL, 'psim:sia:' + repr(identity))
    return AlarmEvent(
        event_id=event_id, timestamp=message.timestamp or received_at,
        account_id=account.account_id, source_type='ALARM_PANEL',
        device_hardware_id=account.hardware_id,
        zone_partition=match['partition'] or account.default_partition,
        zone_number=int(match['zone']), sia_code=match['code'],
        event_status=status, priority_level=priority, correlation_id=None,
    )


class SIAReceiver:
    """Serialize publication/deduplication across concurrent TCP connections.

    The retry cache is bounded and in memory; it is not durable delivery.
    Invalid frames close the connection without ACK; no NAK/DUH is fabricated.
    """

    def __init__(self, accounts, publisher, max_frame_bytes=4095,
                 read_timeout=10, max_clock_skew=20,
                 dedup_seconds=120, dedup_capacity=1024,
                 now=None, monotonic=None, max_connections=16,
                 publish_timeout=5, supervisor=None):
        if (not accounts or not 1 <= max_frame_bytes <= 4095
                or min(read_timeout, max_clock_skew, dedup_seconds,
                       dedup_capacity, max_connections, publish_timeout) <= 0):
            raise ValueError('invalid SIA receiver configuration')
        if any(key != account.account_id for key, account in accounts.items()):
            raise ValueError('SIA account registry mismatch')
        self.accounts = accounts
        self.publisher = publisher
        self.max_frame_bytes = max_frame_bytes
        self.read_timeout = read_timeout
        self.max_clock_skew = max_clock_skew
        self.dedup_seconds = dedup_seconds
        self.dedup_capacity = dedup_capacity
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        if supervisor is not None and supervisor.accounts != accounts:
            raise ValueError('SIA supervision/receiver account mismatch')
        self.supervisor = supervisor
        self.lock = (
            supervisor.lock if supervisor is not None else asyncio.Lock()
        )
        self.seen = OrderedDict()
        self.max_connections = max_connections
        self.connections = set()
        self.publish_timeout = publish_timeout

    async def process(self, frame: bytes) -> bytes:
        """Return ACK only after successful processing, or a safe rejection."""
        message = parse_message(frame, self.accounts, self.max_frame_bytes)
        account = self.accounts[message.account]
        async with self.lock:
            now = self.now()
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError('receiver clock must be timezone-aware')
            if message.timestamp is not None and abs(
                (now - message.timestamp).total_seconds(),
            ) > self.max_clock_skew:
                raise SIAProtocolError('SIA timestamp outside accepted window')
            event = translate_message(message, account, now)
            fresh = True
            if event is not None:
                identity = (message.account, message.sequence, message.data,
                            message.timestamp)
                clock = self.monotonic()
                while self.seen:
                    oldest = next(iter(self.seen))
                    if clock - self.seen[oldest] < self.dedup_seconds:
                        break
                    self.seen.popitem(last=False)
                if identity not in self.seen:
                    # Paho waits for PUBACK in a worker; the asyncio loop keeps
                    # accepting bounded connections and timing out idle peers.
                    await asyncio.to_thread(
                        self.publisher.publish, event,
                        timeout=self.publish_timeout,
                    )
                    self.seen[identity] = self.monotonic()
                    while len(self.seen) > self.dedup_capacity:
                        self.seen.popitem(last=False)
                else:
                    fresh = False
            if self.supervisor is not None and fresh:
                self.supervisor.observe(message, event, now)
        return acknowledge(message, account, now)

    async def read_frame(self, reader):
        """Read LF+CRC+length, then exactly the declared body and CR."""
        header = await reader.readexactly(9)
        if not re.fullmatch(rb'\n[0-9A-Fa-f]{4}0[0-9A-Fa-f]{3}', header):
            raise SIAProtocolError('invalid TCP DC-09 header')
        length = int(header[5:9], 16)
        if not 0 < length <= self.max_frame_bytes:
            raise SIAProtocolError('TCP DC-09 frame exceeds limit')
        return header + await reader.readexactly(length + 1)

    async def handle_client(self, reader, writer):
        """Handle fragmented and concatenated TCP frames until EOF/error."""
        if len(self.connections) >= self.max_connections:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            return
        self.connections.add(writer)
        try:
            while True:
                frame = await asyncio.wait_for(
                    self.read_frame(reader), self.read_timeout,
                )
                response = await self.process(frame)
                writer.write(response)
                await asyncio.wait_for(writer.drain(), self.read_timeout)
        except asyncio.IncompleteReadError:
            pass
        except (ValueError, RuntimeError, OSError, TimeoutError):
            LOGGER.warning('SIA frame rejected or publication failed')
        finally:
            self.connections.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


def account_from_settings(settings):
    """Load one provisioned account; runtime key never enters YAML or logs."""
    raw_key = os.getenv(settings['key_env'])
    key = None
    if raw_key:
        if not re.fullmatch(r'(?:[0-9A-Fa-f]{32}|[0-9A-Fa-f]{64})', raw_key):
            raise ValueError('SIA AES key must be 32 or 64 hex digits')
        key = bytes.fromhex(raw_key)
    account_id = os.getenv(settings['account_env'])
    hardware_id = os.getenv(settings['device_env'])
    if not account_id or not hardware_id:
        raise ValueError('SIA account/device environment variables required')
    return SIAAccount(
        account_id, hardware_id, settings['default_partition'], key,
        settings['allow_plaintext'],
    )


async def serve(settings, account):
    """Run the local TCP receiver with its own MQTT client ID."""
    mqtt_settings = settings['mqtt']
    sia_settings = settings['integrations']['sia_dc09']
    queue_limit = sia_settings.get('mqtt_max_queued_messages', 128)
    if not isinstance(queue_limit, int) or queue_limit <= 0:
        raise ValueError('SIA MQTT queue limit must be a positive integer')
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f'psim-sia-{uuid4()}')
    client.max_queued_messages_set(queue_limit)
    publisher = EventPublisher(
        mqtt_settings['host'], mqtt_settings['port'],
        mqtt_settings['keepalive'],
        client=client,
    )
    try:
        await asyncio.to_thread(publisher.connect)
        accounts = {account.account_id: account}
        supervisor = supervisor_from_settings(
            sia_settings.get('supervision', {'enabled': False}),
            accounts, publisher,
        )
        receiver = SIAReceiver(
            accounts, publisher,
            max_frame_bytes=sia_settings['max_frame_bytes'],
            read_timeout=sia_settings['read_timeout_seconds'],
            max_clock_skew=sia_settings['max_clock_skew_seconds'],
            dedup_seconds=sia_settings['dedup_seconds'],
            dedup_capacity=sia_settings['dedup_capacity'],
            max_connections=sia_settings['max_connections'],
            publish_timeout=sia_settings['publish_timeout_seconds'],
            supervisor=supervisor,
        )
        server = await asyncio.start_server(
            receiver.handle_client, sia_settings['host'], sia_settings['port'],
            limit=sia_settings['max_frame_bytes'] + 10,
        )
        async with server:
            async with asyncio.TaskGroup() as tasks:
                if supervisor is not None:
                    tasks.create_task(supervisor.run())
                await server.serve_forever()
    finally:
        await asyncio.to_thread(publisher.close)


def main():
    """Start using local configuration without printing sensitive errors."""
    settings = load_settings()
    try:
        account = account_from_settings(settings['integrations']['sia_dc09'])
        asyncio.run(serve(settings, account))
    except KeyboardInterrupt:
        pass
    except (ValueError, RuntimeError, OSError, ExceptionGroup):
        raise SystemExit('SIA receiver failed; check local settings/services')


if __name__ == '__main__':
    main()
