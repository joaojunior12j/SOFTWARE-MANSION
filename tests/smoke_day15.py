"""Real AES/TCP supervision, MQTT and database/CEP smoke; synthetic devices."""

import asyncio
from datetime import datetime, timezone
from threading import Event
from uuid import uuid4

import paho.mqtt.client as mqtt
from sqlalchemy import text

from backend.api.schemas import AlarmEvent
from backend.core.correlation_engine import CorrelationEngine
from backend.core.correlation_rules import build_rules
from backend.core.event_bus import EventPublisher
from backend.core.settings import load_settings
from backend.db.alarm_repository import AlarmRepository
from backend.db.consumer import EventConsumer
from backend.db.correlation_repository import CorrelationRepository
from backend.db.repository import EventRepository
from backend.integrations.sia_dc09 import SIAAccount, parse_message
from backend.integrations.sia_dc09_listener import SIAReceiver
from backend.integrations.sia_supervision import SIACommunicationSupervisor
from tests.smoke_day14 import wire


ACCOUNT = SIAAccount('E015', 'PANEL-SMOKE-D15', key=bytes(range(16)))
ACCOUNTS = {ACCOUNT.account_id: ACCOUNT}


async def send_rp(receiver, port):
    """Send an encrypted RP through an actual loopback TCP connection."""
    reader, writer = await asyncio.open_connection('127.0.0.1', port)
    try:
        payload = wire(ACCOUNT, code='RP')
        writer.write(payload[:8])
        await writer.drain()
        writer.write(payload[8:])
        await writer.drain()
        response = await asyncio.wait_for(receiver.read_frame(reader), 5)
        ack = parse_message(response, ACCOUNTS)
        if ack.token != 'ACK' or not ack.encrypted:
            raise RuntimeError('supervision RP missing encrypted ACK')
    finally:
        writer.close()
        await writer.wait_closed()


def sensor_event(hardware, source, status, code):
    """Make camera/PIR inputs; timeout itself must come from the supervisor."""
    return AlarmEvent(
        event_id=uuid4(), timestamp=datetime.now(timezone.utc),
        account_id=ACCOUNT.account_id, source_type=source,
        device_hardware_id=hardware, zone_partition='01', zone_number=1,
        sia_code=code, event_status=status, priority_level='HIGH',
        correlation_id=None,
    )


async def exercise_tcp(publisher, lost, restored):
    """Use actual scheduler deadlines; one outage, then a valid RP recovery."""
    supervisor = SIACommunicationSupervisor(
        ACCOUNTS, publisher, timeout_seconds=1.2, check_interval=0.05,
    )
    receiver = SIAReceiver(ACCOUNTS, publisher, supervisor=supervisor)
    server = await asyncio.start_server(receiver.handle_client, '127.0.0.1', 0)
    task = asyncio.create_task(supervisor.run())
    try:
        async with server:
            port = server.sockets[0].getsockname()[1]
            await send_rp(receiver, port)
            if not await asyncio.to_thread(lost.wait, 5):
                raise RuntimeError('supervision did not publish timeout')
            await asyncio.sleep(0.15)
            await send_rp(receiver, port)
            if not await asyncio.to_thread(restored.wait, 5):
                raise RuntimeError('supervision did not publish return')
            camera = sensor_event('CAMERA-SMOKE-D15', 'CAMERA',
                                  'DISCONNECTED', 'TA')
            pir = sensor_event('PIR-SMOKE-D15', 'PERIMETER_SENSOR',
                               'ACTIVE', 'BA')
            for event in (camera, pir):
                await asyncio.to_thread(publisher.publish, event, timeout=5)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class TrackedCorrelations(CorrelationRepository):
    """Remember only this smoke's generated IDs for exact cleanup."""

    def __init__(self, engine):
        super().__init__(engine=engine)
        self.ids = []

    async def save(self, result):
        self.ids.append(str(result.correlation_id))
        await super().save(result)


async def check_database(settings, events):
    """Verify the consumer path and alarm representation."""
    repository = EventRepository(settings['database']['url'])
    alarms = AlarmRepository(engine=repository.engine)
    correlations = TrackedCorrelations(repository.engine)
    engine = CorrelationEngine(60, rules=build_rules(settings))
    consumer = EventConsumer(
        'localhost', 1883, 60, 'unused', repository,
        asyncio.get_running_loop(),
        correlation_engine=engine, correlation_repository=correlations,
        alarm_repository=alarms,
    )
    ids = [str(event.event_id) for event in events]
    operator_id = uuid4()
    try:
        for event in events:
            await consumer._persist_and_correlate(
                event, event.model_dump(mode='json'),
            )
        loss = next(event for event in events
                    if event.event_status == 'TIMEOUT_SIA_DC09')
        # Repeat the projection to verify idempotency in the real database.
        await alarms.record_communication_timeout(loss)
        rows = await alarms.list_active()
        direct = [alarm for alarm in rows if alarm.alarm_id == loss.event_id]
        if (len(direct) != 1 or direct[0].priority_level != 'HIGH'
                or direct[0].state != 'UNACKNOWLEDGED'
                or direct[0].correlation_id is not None
                or direct[0].sia_codes != ['RP']):
            raise RuntimeError('communication alarm projection failed')
        jammer = [alarm for alarm in rows
                  if str(alarm.correlation_id) in correlations.ids]
        if (len(jammer) != 1 or jammer[0].rule_triggered != 'R01_JAMMER'
                or jammer[0].priority_level != 'CRITICAL'):
            raise RuntimeError('supervision event did not feed R01')
        async with repository.engine.begin() as connection:
            await connection.execute(text(
                "INSERT INTO users (user_id, name, email, role) "
                "VALUES (:id, 'Smoke Day 15', :email, 'OPERATOR')",
            ), {'id': str(operator_id),
                'email': f'smoke-day15-{operator_id}@example.invalid'})
        acknowledged = await alarms.acknowledge(loss.event_id, operator_id)
        if (acknowledged.state != 'ACKNOWLEDGED'
                or acknowledged.sia_codes != ['RP']):
            raise RuntimeError('communication alarm ACK or SIA codes failed')
    finally:
        async with repository.engine.begin() as connection:
            await connection.execute(text(
                'DELETE FROM alarms '
                'WHERE alarm_id = ANY(CAST(:ids AS UUID[])) '
                'OR correlation_id = ANY(CAST(:correlations AS UUID[]))',
            ), {'ids': ids, 'correlations': correlations.ids})
            await connection.execute(text(
                'DELETE FROM events '
                'WHERE event_id = ANY(CAST(:ids AS UUID[]))',
            ), {'ids': ids})
            await connection.execute(text(
                'DELETE FROM correlations WHERE correlation_id = '
                'ANY(CAST(:ids AS UUID[]))',
            ), {'ids': correlations.ids})
            await connection.execute(text(
                'DELETE FROM users WHERE user_id = :id',
            ), {'id': str(operator_id)})
        await repository.close()


def run():
    """Receive canonical QoS 1 events, then verify persistence and R01."""
    settings = load_settings()
    mqtt_settings = settings['mqtt']
    ready, lost, restored, complete = Event(), Event(), Event(), Event()
    captured = []
    subscriber = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=f'psim-day15-sub-{uuid4()}')

    def on_connect(client, userdata, flags, reason, properties):
        if not reason.is_failure:
            client.subscribe(f'mansao/{ACCOUNT.account_id}/eventos/#', qos=1)

    def on_subscribe(client, userdata, mid, reasons, properties):
        if all(not code.is_failure for code in reasons):
            ready.set()

    def on_message(client, userdata, message):
        event = AlarmEvent.model_validate_json(message.payload)
        captured.append((event, message.qos, message.topic))
        if event.event_status == 'TIMEOUT_SIA_DC09':
            lost.set()
        if event.event_status == 'RESTORED':
            restored.set()
        if len(captured) >= 6:
            complete.set()

    subscriber.on_connect = on_connect
    subscriber.on_subscribe = on_subscribe
    subscriber.on_message = on_message
    publisher = EventPublisher(
        mqtt_settings['host'], mqtt_settings['port'],
        mqtt_settings['keepalive'],
        client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                           client_id=f'psim-day15-pub-{uuid4()}'),
    )
    try:
        subscriber.connect(mqtt_settings['host'], mqtt_settings['port'])
        subscriber.loop_start()
        if not ready.wait(5):
            raise RuntimeError('MQTT SUBACK missing')
        publisher.connect()
        asyncio.run(exercise_tcp(publisher, lost, restored))
        if not complete.wait(5):
            raise RuntimeError('supervision smoke events missing')
        events = [event for event, qos, _ in captured]
        if any(qos != 1 for _, qos, _ in captured):
            raise RuntimeError('unexpected delivery QoS')
        for status in ('TIMEOUT_SIA_DC09', 'RESTORED'):
            if sum(event.event_status == status for event in events) != 1:
                raise RuntimeError('unexpected repeated health transition')
        asyncio.run(check_database(settings, events))
    finally:
        publisher.close()
        subscriber.disconnect()
        subscriber.loop_stop()
    print('sia_tcp_aes=ok timeout_once=ok recovery=ok mqtt_qos1=ok '
          'communication_alarm=HIGH r01=CRITICAL operator_ack=ok '
          'database=ok cleanup=ok')


if __name__ == '__main__':
    run()
