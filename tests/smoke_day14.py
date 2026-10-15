"""Real local TCP → SIA AES → MQTT QoS 1 smoke with synthetic accounts."""

import asyncio
from datetime import datetime, timezone
from threading import Event
from uuid import uuid4

import paho.mqtt.client as mqtt

from backend.api.schemas import AlarmEvent
from backend.core.event_bus import EventPublisher
from backend.core.settings import load_settings
from backend.integrations.sia_dc09 import (
    SIAAccount, STAMP, encrypt_content, frame_body, parse_message,
)
from backend.integrations.sia_dc09_listener import SIAReceiver


ACCOUNTS = {
    'D014': SIAAccount('D014', 'PANEL-SMOKE-128', key=bytes(range(16))),
    'D015': SIAAccount('D015', 'PANEL-SMOKE-256', key=bytes(range(32))),
}


def wire(account, code='BA', token='SIA-DCS', encrypted=True):
    """Make fresh synthetic frames without using local equipment secrets."""
    stamp = datetime.now(timezone.utc).strftime(STAMP)
    data = ''
    if token == 'SIA-DCS':
        data = f'#{account.account_id}|Nri01/{code}003'
    clear = (data + ']_' + stamp).encode()
    content = encrypt_content(clear, account.key) if encrypted else clear
    header = (f'"{"*" if encrypted else ""}{token}"0001L0'
              f'#{account.account_id}[').encode()
    return frame_body(header + content)


class CountingPublisher:
    """Count handoffs while using the real publisher and broker."""

    def __init__(self, publisher):
        self.publisher = publisher
        self.count = 0

    def publish(self, event, timeout=None):
        result = self.publisher.publish(event, timeout=timeout)
        self.count += 1
        return result


async def exchange(receiver, port, payload, replies=1):
    """Send split TCP bytes and collect ACKs or confirm rejection."""
    reader, writer = await asyncio.open_connection('127.0.0.1', port)
    try:
        writer.write(payload[:7])
        await writer.drain()
        writer.write(payload[7:])
        await writer.drain()
        messages = []
        for _ in range(replies):
            response = await asyncio.wait_for(receiver.read_frame(reader), 3)
            messages.append(parse_message(response, ACCOUNTS))
        if replies == 0 and await asyncio.wait_for(reader.read(1), 3) != b'':
            raise RuntimeError('rejected SIA frame was acknowledged')
        if any(msg.token != 'ACK' or not msg.encrypted for msg in messages):
            raise RuntimeError('expected encrypted ACK')
    finally:
        writer.close()
        await writer.wait_closed()


async def check_tcp(publisher):
    """Exercise real framing, AES, retries and rejected frames."""
    receiver = SIAReceiver(ACCOUNTS, publisher)
    server = await asyncio.start_server(receiver.handle_client, '127.0.0.1', 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        first = wire(ACCOUNTS['D014'])
        await exchange(receiver, port, first + first, replies=2)
        await exchange(receiver, port, wire(ACCOUNTS['D015'], code='TA'))
        await exchange(receiver, port, wire(ACCOUNTS['D014'], token='NULL'))
        await exchange(receiver, port,
                       wire(ACCOUNTS['D014'], encrypted=False), replies=0)
        invalid = bytearray(first)
        invalid[1] = ord('0') if first[1] != ord('0') else ord('1')
        await exchange(receiver, port, bytes(invalid), replies=0)
    if publisher.count != 2:
        raise RuntimeError('duplicate/control/rejected frame reached MQTT')


def run():
    """Verify the JSON contract and QoS at the broker subscriber."""
    settings = load_settings()['mqtt']
    ready, received = Event(), Event()
    captured = []
    subscriber = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=f'psim-sia-smoke-sub-{uuid4()}')

    def on_connect(client, userdata, flags, reason, properties):
        if not reason.is_failure:
            client.subscribe([
                (f'mansao/{account}/eventos/centrais', 1)
                for account in ACCOUNTS
            ])

    def on_subscribe(client, userdata, mid, reasons, properties):
        if len(reasons) == 2 and all(not item.is_failure for item in reasons):
            ready.set()

    def on_message(client, userdata, message):
        captured.append((message.topic, message.qos, message.payload))
        if len(captured) >= 2:
            received.set()

    subscriber.on_connect = on_connect
    subscriber.on_subscribe = on_subscribe
    subscriber.on_message = on_message
    publisher = EventPublisher(
        settings['host'], settings['port'], settings['keepalive'],
        client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                           client_id=f'psim-sia-smoke-pub-{uuid4()}'),
    )
    try:
        subscriber.connect(settings['host'], settings['port'])
        subscriber.loop_start()
        if not ready.wait(5):
            raise RuntimeError('MQTT SUBACK missing')
        publisher.connect()
        asyncio.run(check_tcp(CountingPublisher(publisher)))
        if not received.wait(5):
            raise RuntimeError('canonical SIA events did not arrive')
        codes = set()
        for topic, qos, payload in captured:
            event = AlarmEvent.model_validate_json(payload)
            fields_match = (
                set(event.model_dump()) == set(AlarmEvent.model_fields)
            )
            if (qos != 1 or not fields_match
                    or topic != f'mansao/{event.account_id}/eventos/centrais'):
                raise RuntimeError('unexpected SIA topic, QoS or contract')
            codes.add(event.sia_code)
        if codes != {'BA', 'TA'}:
            raise RuntimeError('unexpected SIA events')
    finally:
        publisher.close()
        subscriber.disconnect()
        subscriber.loop_stop()
    print('sia_tcp=ok aes128_256=ok encrypted_ack=ok retry_cache=ok '
          'reject=ok mqtt_qos1=ok fixed_payload=ok')


if __name__ == '__main__':
    run()
