"""Clock-controlled SIA supervision, recovery and operational alarm tests."""

import asyncio
from datetime import timedelta
import unittest
from unittest.mock import AsyncMock, Mock

from backend.api.schemas import AlarmEvent
from backend.core.correlation_engine import CorrelationEngine
from backend.core.correlation_rules import JammerRule
from backend.db.alarm_repository import AlarmRepository
from backend.db.consumer import EventConsumer
from backend.integrations.sia_dc09 import SIAAccount, SIAProtocolError
from backend.integrations.sia_dc09_listener import SIAReceiver
from backend.integrations.sia_supervision import (
    SIACommunicationSupervisor, supervisor_from_settings,
)
from tests.test_sia_dc09 import ACCOUNT, ACCOUNTS, NOW, packet


class Clock:
    """Independent monotonic and UTC clocks for deadline/jump tests."""

    def __init__(self):
        self.seconds = 0
        self.wall_shift = 0

    def monotonic(self):
        return self.seconds

    def utc(self):
        return NOW + timedelta(seconds=self.seconds + self.wall_shift)


class Publisher:
    """Record attempts and confirmed deliveries independently."""

    def __init__(self):
        self.events = []
        self.attempts = []
        self.fail_status = None

    def publish(self, event, timeout=None):
        self.attempts.append(event)
        if event.event_status == self.fail_status:
            raise TimeoutError('synthetic transport error')
        self.events.append(event)


class SupervisionTests(unittest.IsolatedAsyncioTestCase):
    """Verify timeout/recovery and replay safety through the real receiver."""

    def setUp(self):
        self.clock = Clock()
        self.publisher = Publisher()
        self.supervisor = SIACommunicationSupervisor(
            ACCOUNTS, self.publisher, timeout_seconds=10,
            now=self.clock.utc, monotonic=self.clock.monotonic,
        )
        self.receiver = SIAReceiver(
            ACCOUNTS, self.publisher, now=self.clock.utc,
            monotonic=self.clock.monotonic, supervisor=self.supervisor,
        )

    async def rp(self, seq='0001', stamp=None):
        return await self.receiver.process(packet(
            '#1234|Nri01/RP000', encrypted=True, sequence=seq,
            stamp=stamp or self.clock.utc(),
        ))

    async def expire(self):
        self.clock.seconds = 10
        await self.supervisor.check_once()

    async def test_initial_grace_exact_boundary_and_one_event_per_outage(self):
        self.clock.seconds = 9.999
        self.assertEqual(await self.supervisor.check_once(), 0)
        await self.expire()
        event = self.publisher.events[0]
        self.assertEqual(set(event.model_dump()), set(AlarmEvent.model_fields))
        self.assertEqual(event.event_status, 'TIMEOUT_SIA_DC09')
        self.assertEqual(event.priority_level, 'HIGH')
        self.assertEqual(event.source_type, 'ALARM_PANEL')
        self.assertEqual(event.sia_code, 'RP')
        self.assertEqual(event.device_hardware_id, ACCOUNT.hardware_id)
        self.assertEqual(event.zone_number, 0)
        self.assertIsNone(event.correlation_id)
        self.clock.seconds = 1000
        self.assertEqual(await self.supervisor.check_once(), 0)
        self.assertEqual(len(self.publisher.events), 1)

    async def test_fresh_rp_renews_recovery_and_new_outage_is_distinct(self):
        self.clock.seconds = 9
        await self.rp()
        self.clock.seconds = 18
        self.assertEqual(await self.supervisor.check_once(), 0)
        self.clock.seconds = 19
        await self.supervisor.check_once()
        loss = self.publisher.events[-1]
        self.clock.seconds = 20
        await self.rp('0002')
        self.assertEqual(await self.supervisor.check_once(), 1)
        restored = self.publisher.events[-1]
        self.assertEqual(restored.event_status, 'RESTORED')
        self.assertEqual(restored.priority_level, 'LOW')
        self.assertEqual(restored.zone_number, 0)
        self.clock.seconds = 30
        await self.supervisor.check_once()
        self.assertNotEqual(self.publisher.events[-1].event_id, loss.event_id)
        self.assertEqual(self.publisher.events[-1].event_status,
                         'TIMEOUT_SIA_DC09')

    async def test_non_rp_and_null_do_not_renew_default_policy(self):
        self.clock.seconds = 9
        await self.receiver.process(packet(stamp=self.clock.utc()))
        await self.receiver.process(packet('', token='NULL', encrypted=True,
                                           stamp=self.clock.utc()))
        await self.expire()
        self.assertEqual(self.publisher.events[-1].event_status,
                         'TIMEOUT_SIA_DC09')

    async def test_any_valid_mode_renews_without_fabricating_rp(self):
        self.supervisor.heartbeat_mode = 'any_valid_message'
        self.clock.seconds = 9
        await self.receiver.process(packet('', token='NULL', encrypted=True,
                                           stamp=self.clock.utc()))
        self.assertEqual(self.publisher.events, [])
        self.clock.seconds = 18
        self.assertEqual(await self.supervisor.check_once(), 0)
        self.clock.seconds = 19
        await self.supervisor.check_once()
        self.assertEqual(self.publisher.events[0].event_status,
                         'TIMEOUT_SIA_DC09')

    async def test_retransmissions_old_timestamps_and_rejected_frames(self):
        self.clock.seconds = 1
        await self.rp()
        self.clock.seconds = 9
        await self.rp(stamp=NOW + timedelta(seconds=1))
        await self.rp('0002', stamp=NOW)
        with self.assertRaises(SIAProtocolError):
            await self.receiver.process(packet('#9999|Nri01/RP000'))
        with self.assertRaises(SIAProtocolError):
            await self.receiver.process(packet(stamp=NOW - timedelta(hours=1)))
        with self.assertRaises(SIAProtocolError):
            await self.receiver.process(b'invalid CRC')
        self.clock.seconds = 11
        await self.supervisor.check_once()
        self.assertEqual(self.publisher.events[-1].event_status,
                         'TIMEOUT_SIA_DC09')

    async def test_untimed_plaintext_retry_does_not_keep_alive(self):
        self.clock.seconds = 1
        wire = packet('#1234|Nri01/RP000', stamp=None)
        await self.receiver.process(wire)
        self.clock.seconds = 9
        await self.receiver.process(wire)
        self.clock.seconds = 11
        await self.supervisor.check_once()
        self.assertEqual(self.publisher.events[-1].event_status,
                         'TIMEOUT_SIA_DC09')

    async def test_receiver_publish_failure_does_not_renew_supervision(self):
        self.clock.seconds = 9
        self.publisher.fail_status = 'ACTIVE'
        with self.assertRaises(TimeoutError):
            await self.rp()
        self.publisher.fail_status = None
        await self.expire()
        self.assertEqual(self.publisher.events[-1].event_status,
                         'TIMEOUT_SIA_DC09')

    async def test_mqtt_retry_keeps_loss_id_and_order_before_return(self):
        self.publisher.fail_status = 'TIMEOUT_SIA_DC09'
        with self.assertLogs('backend.integrations.sia_supervision'):
            await self.expire()
        loss = self.publisher.attempts[-1]
        self.clock.seconds = 11
        await self.rp()
        self.publisher.fail_status = None
        self.assertEqual(await self.supervisor.check_once(), 2)
        transitions = [event for event in self.publisher.events
                       if event.event_status != 'ACTIVE']
        self.assertEqual(transitions[0].event_id, loss.event_id)
        self.assertEqual(transitions[0].timestamp, loss.timestamp)
        self.assertEqual([event.event_status for event in transitions],
                         ['TIMEOUT_SIA_DC09', 'RESTORED'])

    async def test_recovery_retry_does_not_repeat_loss_and_retains_uuid(self):
        await self.expire()
        self.clock.seconds = 11
        await self.rp()
        self.publisher.fail_status = 'RESTORED'
        with self.assertLogs('backend.integrations.sia_supervision'):
            await self.supervisor.check_once()
        restoration = self.publisher.attempts[-1]
        self.publisher.fail_status = None
        await self.supervisor.check_once()
        self.assertEqual(self.publisher.events[-1].event_id,
                         restoration.event_id)
        self.assertEqual(len([event for event in self.publisher.events
                              if event.event_status == 'TIMEOUT_SIA_DC09']), 1)

    async def test_clock_jump_does_not_expire_healthy_account(self):
        self.clock.wall_shift = 86400
        self.assertEqual(await self.supervisor.check_once(), 0)
        self.clock.seconds = 10
        await self.supervisor.check_once()
        self.assertEqual(self.publisher.events[0].timestamp, self.clock.utc())

    async def test_account_timeout_isolation(self):
        second = SIAAccount('5678', 'SECOND-TEST', key=ACCOUNT.key)
        supervisor = SIACommunicationSupervisor(
            {**ACCOUNTS, '5678': second}, self.publisher,
            timeout_seconds=10, account_timeouts={'5678': 20},
            now=self.clock.utc, monotonic=self.clock.monotonic,
        )
        self.clock.seconds = 10
        await supervisor.check_once()
        self.assertEqual([event.account_id for event in self.publisher.events],
                         ['1234'])
        self.clock.seconds = 20
        await supervisor.check_once()
        self.assertEqual([event.account_id for event in self.publisher.events],
                         ['1234', '5678'])
        self.assertEqual(len(supervisor.states), 2)

    async def test_background_loop_cancels_cleanly(self):
        self.supervisor.check_interval = 0.001
        signal = asyncio.Event()

        async def checked():
            signal.set()

        self.supervisor.check_once = checked
        task = asyncio.create_task(self.supervisor.run())
        await asyncio.wait_for(signal.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_configuration_and_disabled_mode(self):
        disabled = supervisor_from_settings({'enabled': False}, {}, None)
        self.assertIsNone(disabled)
        for options in ({'timeout_seconds': 0},
                        {'check_interval': float('nan')},
                        {'heartbeat_mode': 'unknown'},
                        {'account_timeouts': {'unknown': 10}},
                        {'timeout_seconds': 0.1, 'check_interval': 1}):
            with self.assertRaises(ValueError):
                SIACommunicationSupervisor(ACCOUNTS, self.publisher, **options)
        with self.assertRaises(ValueError):
            SIAReceiver({}, self.publisher, supervisor=self.supervisor)
        settings = {'enabled': True, 'timeout_seconds': 60,
                    'check_interval_seconds': 1, 'account_timeouts': {},
                    'heartbeat_mode': 'rp', 'publish_timeout_seconds': 5}
        built = supervisor_from_settings(settings, ACCOUNTS, self.publisher)
        self.assertEqual(built.heartbeat_mode, 'rp')


class CommunicationAlarmTests(unittest.IsolatedAsyncioTestCase):
    """Check operational alarm projection without consuming R01 evidence."""

    async def test_projection_filters_return_and_uses_idempotent_id(self):
        publisher = Publisher()
        clock = Clock()
        supervisor = SIACommunicationSupervisor(
            ACCOUNTS, publisher, timeout_seconds=10, now=clock.utc,
            monotonic=clock.monotonic,
        )
        clock.seconds = 10
        await supervisor.check_once()
        loss = publisher.events[0]
        connection = Mock(execute=AsyncMock())
        context = AsyncMock()
        context.__aenter__.return_value = connection
        engine = Mock()
        engine.begin.return_value = context
        repository = AlarmRepository(engine=engine)
        await repository.record_communication_timeout(loss)
        statement, params = connection.execute.call_args.args
        self.assertIn('ON CONFLICT (alarm_id) DO NOTHING', str(statement))
        self.assertEqual(params['alarm_id'], str(loss.event_id))
        self.assertIsNone(loss.correlation_id)
        await repository.record_communication_timeout(loss.model_copy(
            update={'event_status': 'RESTORED'},
        ))
        connection.execute.assert_awaited_once()

    async def test_consumer_stores_alarm_and_retains_r01_evidence(self):
        publisher = Publisher()
        clock = Clock()
        supervisor = SIACommunicationSupervisor(
            ACCOUNTS, publisher, timeout_seconds=10, now=clock.utc,
            monotonic=clock.monotonic,
        )
        clock.seconds = 10
        await supervisor.check_once()
        loss = publisher.events[0]
        engine = CorrelationEngine(60, rules=(JammerRule(15),))
        repository = Mock(save=AsyncMock())
        alarms = Mock(record_communication_timeout=AsyncMock())
        consumer = EventConsumer('localhost', 1883, 60, 'test', repository,
                                 asyncio.get_running_loop(), client=Mock(),
                                 correlation_engine=engine,
                                 correlation_repository=Mock(save=AsyncMock()),
                                 alarm_repository=alarms)
        await consumer._persist_and_correlate(
            loss, loss.model_dump(mode='json'),
        )
        repository.save.assert_awaited_once()
        alarms.record_communication_timeout.assert_awaited_once_with(loss)
        evidence = engine.events_for('1234', '01')
        self.assertEqual(evidence[0].event_id, loss.event_id)
        self.assertIsNone(evidence[0].correlation_id)
