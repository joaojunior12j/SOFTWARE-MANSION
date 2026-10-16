"""ADM-CID over real AES/TCP, MQTT QoS 1 and database; synthetic accounts."""

import asyncio
from datetime import datetime, timezone
from threading import Event
from uuid import uuid4

import paho.mqtt.client as mqtt
from sqlalchemy import text

from backend.api.schemas import AlarmEvent
from backend.core.event_bus import EventPublisher
from backend.core.settings import load_settings
from backend.db.repository import EventRepository
from backend.integrations.sia_dc09 import (
    SIAAccount, STAMP, encrypt_content, frame_body, parse_message,
)
from backend.integrations.sia_dc09_listener import SIAReceiver
from tests.smoke_day14 import CountingPublisher


ACCOUNTS = {
    'E016': SIAAccount('E016', 'CID-SMOKE-128', key=bytes(range(16))),
    'E017': SIAAccount('E017', 'CID-SMOKE-256', key=bytes(range(32))),
}


def wire(account, digits, sequence):
    """Encode the documented ADM-CID payload, without real panel secrets."""
    stamp = datetime.now(timezone.utc).strftime(STAMP)
    clear = f'#{account.account_id}|{digits} 02 001]_{stamp}'.encode()
    header = (f'"*ADM-CID"{sequence:04d}L0'
              f'#{account.account_id}[').encode()
    return frame_body(header + encrypt_content(clear, account.key))


async def exercise(publisher):
    """Validate fragmented/concatenated TCP, retry ACKs and safe rejection."""
    receiver = SIAReceiver(ACCOUNTS, publisher)
    server = await asyncio.start_server(receiver.handle_client, '127.0.0.1', 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        for account in ACCOUNTS.values():
            reader, writer = await asyncio.open_connection('127.0.0.1', port)
            try:
                frames = [wire(account, code, index)
                          for index, code in enumerate(
                              ('1130', '3130', '1137', '3137', '1602'), 1)]
                payload = frames[0] + b''.join(frames)  # Retry first frame.
                writer.write(payload[:5])
                await writer.drain()
                writer.write(payload[5:])
                await writer.drain()
                for sequence in (1, 1, 2, 3, 4, 5):
                    ack = parse_message(await asyncio.wait_for(
                        receiver.read_frame(reader), 5), ACCOUNTS)
                    if (ack.token != 'ACK' or not ack.encrypted
                            or int(ack.sequence) != sequence):
                        raise RuntimeError('invalid Contact ID ACK')
                writer.write(wire(account, '1400', 6))
                await writer.drain()
                if await asyncio.wait_for(reader.read(1), 5) != b'':
                    raise RuntimeError('unsupported code was acknowledged')
            finally:
                writer.close()
                await writer.wait_closed()
    if publisher.count != 10:
        raise RuntimeError('retry or unsupported code reached MQTT')


async def persist(settings, events):
    """Save broker payloads twice and clean up only generated IDs."""
    repository = EventRepository(settings['database']['url'])
    ids = [str(event.event_id) for event in events]
    try:
        for event in events:
            for _ in range(2):
                await repository.save(event, event.model_dump(mode='json'))
        async with repository.engine.connect() as connection:
            rows = (await connection.execute(text(
                'SELECT raw_payload FROM events '
                'WHERE event_id = ANY(CAST(:ids AS UUID[]))',
            ), {'ids': ids})).scalars().all()
        expected = {str(event.event_id): event.model_dump(mode='json')
                    for event in events}
        if (len(rows) != 10
                or any(row != expected[row['event_id']] for row in rows)):
            raise RuntimeError('Contact ID database verification failed')
    finally:
        try:
            async with repository.engine.begin() as connection:
                await connection.execute(text(
                    'DELETE FROM events '
                    'WHERE event_id = ANY(CAST(:ids AS UUID[]))',
                ), {'ids': ids})
        finally:
            await repository.close()


def run():
    """Observe real broker events and check database persistence."""
    settings = load_settings()
    mqtt_settings = settings['mqtt']
    ready, complete = Event(), Event()
    captured = []
    subscriber = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=f'psim-cid-sub-{uuid4()}')

    def on_connect(client, userdata, flags, reason, properties):
        if not reason.is_failure:
            client.subscribe([(f'mansao/{acct}/eventos/centrais', 1)
                              for acct in ACCOUNTS])

    def on_subscribe(client, userdata, mid, reasons, properties):
        if len(reasons) == 2 and all(not code.is_failure for code in reasons):
            ready.set()

    def on_message(client, userdata, message):
        captured.append((message.topic, message.qos, message.payload))
        if len(captured) >= 10:
            complete.set()

    subscriber.on_connect = on_connect
    subscriber.on_subscribe = on_subscribe
    subscriber.on_message = on_message
    publisher = EventPublisher(
        mqtt_settings['host'], mqtt_settings['port'],
        mqtt_settings['keepalive'],
        client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                           client_id=f'psim-cid-pub-{uuid4()}'),
    )
    try:
        subscriber.connect(mqtt_settings['host'], mqtt_settings['port'])
        subscriber.loop_start()
        if not ready.wait(5):
            raise RuntimeError('MQTT SUBACK missing')
        publisher.connect()
        asyncio.run(exercise(CountingPublisher(publisher)))
        if not complete.wait(5) or len(captured) != 10:
            raise RuntimeError('Contact ID MQTT count mismatch')
        events = []
        for topic, qos, payload in captured:
            event = AlarmEvent.model_validate_json(payload)
            expected_topic = f'mansao/{event.account_id}/eventos/centrais'
            fields_match = (
                set(event.model_dump()) == set(AlarmEvent.model_fields)
            )
            if (qos != 1 or topic != expected_topic
                    or not fields_match):
                raise RuntimeError('unexpected Contact ID MQTT contract')
            events.append(event)
        for account in ACCOUNTS:
            codes = [event.sia_code for event in events
                     if event.account_id == account]
            if codes != ['BA', 'BR', 'TA', 'TR', 'RP']:
                raise RuntimeError('unexpected Contact ID code mapping')
        asyncio.run(persist(settings, events))
    finally:
        publisher.close()
        subscriber.disconnect()
        subscriber.loop_stop()
    print('adm_cid_tcp=ok aes128_256=ok ack_retry=ok reject=ok '
          'mqtt_qos1=ok fixed_payload=ok database_idempotency=ok cleanup=ok')


if __name__ == '__main__':
    run()
