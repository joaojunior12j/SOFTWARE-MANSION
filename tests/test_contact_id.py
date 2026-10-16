"""Synthetic Contact ID vectors, shared receiver and supervision regression."""

from dataclasses import replace
from datetime import timedelta
import unittest
from unittest.mock import Mock, patch

from backend.api.schemas import AlarmEvent
from backend.integrations.contact_id_listener import main, translate_contact_id
from backend.integrations.sia_dc09 import (
    SIAAccount, SIAProtocolError, parse_message,
)
from backend.integrations.sia_dc09_listener import SIAReceiver
from backend.integrations.sia_supervision import SIACommunicationSupervisor
from tests.test_sia_dc09 import ACCOUNT, ACCOUNTS, KEY, NOW, packet
from tests.test_sia_supervision import Clock, Publisher


def cid(data='#1234|1130 02 001', **kwargs):
    """Encode ADM-CID syntax documented by Ajax, with synthetic credentials."""
    return packet(data, token='ADM-CID', **kwargs)


class ContactIDTests(unittest.TestCase):
    """Verify explicit mapping and strict rejection of unsupported codes."""

    def test_supported_codes_and_exact_contract(self):
        for digits, code, status, priority in (
            ('1130', 'BA', 'ACTIVE', 'CRITICAL'),
            ('3130', 'BR', 'RESTORED', 'LOW'),
            ('1137', 'TA', 'TAMPER', 'HIGH'),
            ('3137', 'TR', 'RESTORED', 'LOW'),
            ('1602', 'RP', 'ACTIVE', 'LOW'),
        ):
            with self.subTest(digits=digits):
                message = parse_message(
                    cid(f'#1234|{digits} 02 001'), ACCOUNTS,
                )
                event = translate_contact_id(message, ACCOUNT, NOW)
                self.assertEqual(set(event.model_dump()),
                                 set(AlarmEvent.model_fields))
                self.assertEqual((event.sia_code, event.event_status,
                                  event.priority_level),
                                 (code, status, priority))
                self.assertEqual(event.zone_partition, '02')
                self.assertEqual(event.zone_number, 1)
                self.assertEqual(event.device_hardware_id, ACCOUNT.hardware_id)
                self.assertEqual(event.timestamp, NOW)
                self.assertEqual(event.source_type, 'ALARM_PANEL')
                self.assertIsNone(event.correlation_id)

    def test_rejects_unknown_codes_qualifiers_and_wire_variants(self):
        for data in ('#1234|6130 02 001', '#1234|3602 02 001',
                     '#1234|1400 02 001', '#1234|1301 02 001',
                     '#9999|1130 02 001', '#1234|18113002001',
                     '#1234|113002001', '#1234|1130 2 001',
                     '#1234|1130 02 1', '#1234|1130 02 001 ',
                     '#1234|1130  02 001', '#1234|1130 02 001junk'):
            with self.subTest(data=data), self.assertRaises(SIAProtocolError):
                translate_contact_id(parse_message(cid(data), ACCOUNTS),
                                     ACCOUNT, NOW)
        message = parse_message(cid(), ACCOUNTS)
        for changed in (replace(message, token='SIA-DCS'),
                        replace(message, account='9999')):
            with self.assertRaises(SIAProtocolError):
                translate_contact_id(changed, ACCOUNT, NOW)

    def test_dated_identity_stable_and_untimed_identity_unique(self):
        message = parse_message(cid(), ACCOUNTS)
        event = translate_contact_id(message, ACCOUNT, NOW)
        self.assertEqual(event.event_id,
                         translate_contact_id(message, ACCOUNT, NOW).event_id)
        changed = translate_contact_id(replace(message, sequence='0002'),
                                       ACCOUNT, NOW)
        self.assertNotEqual(changed.event_id, event.event_id)
        undated = replace(message, timestamp=None)
        first = translate_contact_id(undated, ACCOUNT, NOW)
        second = translate_contact_id(undated, ACCOUNT, NOW)
        self.assertEqual(first.timestamp, NOW)
        self.assertNotEqual(first.event_id, second.event_id)

    def test_cli_uses_same_listener(self):
        with patch('backend.integrations.sia_dc09_listener.main') as run:
            main()
        run.assert_called_once_with()


class ContactIDReceiverTests(unittest.IsolatedAsyncioTestCase):
    """Exercise AES, ACK, retry and RP policies through actual processing."""

    async def test_aes128_256_and_retry(self):
        for key in (KEY, bytes(range(32))):
            account = SIAAccount('1234', 'CID-TEST', key=key)
            accounts = {'1234': account}
            publisher = Mock()
            receiver = SIAReceiver(accounts, publisher, now=lambda: NOW)
            frame = cid(encrypted=True, key=key)
            for _ in range(2):
                ack = parse_message(await receiver.process(frame), accounts)
                self.assertEqual(ack.token, 'ACK')
                self.assertEqual(ack.sequence, '0001')
                self.assertTrue(ack.encrypted)
            publisher.publish.assert_called_once()

    async def test_publish_failure_retries_same_event_before_ack(self):
        publisher = Mock()
        publisher.publish.side_effect = [TimeoutError(), None]
        receiver = SIAReceiver(ACCOUNTS, publisher, now=lambda: NOW)
        with self.assertRaises(TimeoutError):
            await receiver.process(cid(encrypted=True))
        self.assertFalse(receiver.seen)
        await receiver.process(cid(encrypted=True))
        events = [call.args[0] for call in publisher.publish.call_args_list]
        self.assertEqual(events[0].event_id, events[1].event_id)

    async def test_invalid_messages_never_publish(self):
        publisher = Mock()
        receiver = SIAReceiver(ACCOUNTS, publisher, now=lambda: NOW)
        frames = [cid('#1234|6130 02 001', encrypted=True),
                  cid(stamp=NOW - timedelta(seconds=21), encrypted=True)]
        invalid = bytearray(cid(encrypted=True))
        invalid[1] = ord('X')
        frames.append(bytes(invalid))
        for frame in frames:
            with self.assertRaises(SIAProtocolError):
                await receiver.process(frame)
        publisher.publish.assert_not_called()
        self.assertFalse(receiver.seen)

    async def test_cid_rp_supervision_and_replay_rejection(self):
        clock, publisher = Clock(), Publisher()
        supervisor = SIACommunicationSupervisor(
            ACCOUNTS, publisher, timeout_seconds=10,
            now=clock.utc, monotonic=clock.monotonic,
        )
        receiver = SIAReceiver(
            ACCOUNTS, publisher, supervisor=supervisor,
            now=clock.utc, monotonic=clock.monotonic,
        )
        frame = cid('#1234|1602 00 000', encrypted=True)
        await receiver.process(frame)
        clock.seconds = 9
        await receiver.process(frame)  # Replay cannot postpone deadline.
        await receiver.process(cid(encrypted=True, stamp=clock.utc()))
        with self.assertRaises(SIAProtocolError):
            await receiver.process(cid('#1234|3602 00 000',
                                       encrypted=True, stamp=clock.utc()))
        clock.seconds = 10
        self.assertEqual(await supervisor.check_once(), 1)
        await receiver.process(cid('#1234|1602 00 000', encrypted=True,
                                   sequence='0002', stamp=clock.utc()))
        self.assertEqual(await supervisor.check_once(), 1)
        self.assertEqual([e.event_status for e in publisher.events],
                         ['ACTIVE', 'ACTIVE', 'TIMEOUT_SIA_DC09',
                          'ACTIVE', 'RESTORED'])
