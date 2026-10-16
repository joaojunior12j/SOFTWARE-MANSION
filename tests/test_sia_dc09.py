"""SIA framing, crypto and receiver tests; all credentials are synthetic."""

import asyncio
from datetime import datetime, timedelta, timezone
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from backend.api.schemas import AlarmEvent
from backend.integrations.sia_dc09 import (
    SIAAccount, SIAProtocolError, STAMP, acknowledge, crc16,
    decrypt_content, encrypt_content, frame_body, parse_message, read_body,
)
from backend.integrations.sia_dc09_listener import (
    SIAReceiver, account_from_settings, main, serve, translate_message,
)


NOW = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
KEY = bytes(range(16))  # Public synthetic test key, never a device key.
ACCOUNT = SIAAccount('1234', 'PANEL-TEST', key=KEY, allow_plaintext=True)
ACCOUNTS = {'1234': ACCOUNT}


def packet(data='#1234|Nri01/BA003', encrypted=False, sequence='0001',
           stamp=NOW, token='SIA-DCS', key=KEY):
    """Generate synthetic test traffic with explicit UTC time."""
    header = (f'"{"*" if encrypted else ""}{token}"{sequence}'
              'R0L0#1234[').encode()
    content = data.encode() + b']'
    if stamp is not None:
        content += ('_' + stamp.strftime(STAMP)).encode()
    if encrypted:
        content = encrypt_content(content, key)
    return frame_body(header + content)


class CodecTests(unittest.TestCase):
    """Check independent CRC/ACK vectors and rejected frames."""

    def test_crc_check_value_and_public_null_vector(self):
        self.assertEqual(crc16(b'123456789'), 0xBB3D)
        # Wire example from the SIA subcommittee public reference test suite.
        reference = (b'\n1D85002B"NULL"0001L0#00653210[]'
                     b'_09:17:32,05-18-2016\r')
        account = SIAAccount('00653210', 'TEST', allow_plaintext=True)
        message = parse_message(reference, {'00653210': account})
        self.assertEqual(message.token, 'NULL')
        self.assertEqual(message.timestamp.year, 2016)

    def test_public_encrypted_ack_reference_vector(self):
        # Public interoperability vector, not a local equipment credential.
        key = bytes.fromhex('ABCD' * 8)
        cipher = (b'14F088FF5DCB19D1908069507EAB97C7'
                  b'CDB20F1C6EFA550BB59864D54B2DFA1C')
        self.assertEqual(decrypt_content(cipher, key),
                         b']_16:08:12,04-14-2015')

    def test_plaintext_and_aes_128_256_roundtrip(self):
        for key in (KEY, bytes(range(32))):
            account = SIAAccount('1234', 'TEST', key=key)
            message = parse_message(packet(encrypted=True, key=key),
                                    {'1234': account})
            self.assertTrue(message.encrypted)
            self.assertEqual(message.timestamp, NOW)
            ack = parse_message(acknowledge(message, account, NOW),
                                {'1234': account})
            self.assertEqual(ack.token, 'ACK')
            self.assertEqual(ack.sequence, message.sequence)
            self.assertEqual(ack.timestamp, NOW)
            self.assertTrue(ack.encrypted)
        message = parse_message(packet(), ACCOUNTS)
        self.assertFalse(message.encrypted)
        self.assertEqual(read_body(acknowledge(message, ACCOUNT, NOW)),
                         b'"ACK"0001R0L0#1234[]')

    def test_random_prefix_padding_changes_ciphertext(self):
        self.assertNotEqual(packet(encrypted=True), packet(encrypted=True))
        for length in range(1, 34):
            content = b'a' * length
            decoded = decrypt_content(encrypt_content(content, KEY), KEY)
            self.assertEqual(decoded, content)

    def test_invalid_boundaries_crc_length_and_oversize(self):
        original = packet()
        values = [b'', original[1:], original[:-1],
                  original[:1] + b'0000' + original[5:],
                  original[:5] + b'0001' + original[9:],
                  original[:5] + b'FFFF' + original[9:]]
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(SIAProtocolError):
                    parse_message(value, ACCOUNTS)
        with self.assertRaises(SIAProtocolError):
            read_body(original, max_bytes=5)
        for body in (b'', b'\n', b'x' * 4096):
            with self.assertRaises(SIAProtocolError):
                frame_body(body)

    def test_account_encryption_and_key_policies(self):
        with self.assertRaises(SIAProtocolError):
            parse_message(packet(), {})
        encrypted_only = SIAAccount('1234', 'TEST', key=KEY)
        with self.assertRaises(SIAProtocolError):
            parse_message(packet(), {'1234': encrypted_only})
        plain_only = SIAAccount('1234', 'TEST', allow_plaintext=True)
        with self.assertRaises(SIAProtocolError):
            parse_message(packet(encrypted=True), {'1234': plain_only})
        for key in (b'x', bytes(24)):
            with self.assertRaises(SIAProtocolError):
                encrypt_content(b'test', key)
        with self.assertRaises(ValueError):
            SIAAccount('1234', 'TEST')
        for account_id, device, partition in (
            ('invalid', 'TEST', '01'), ('1234', '', '01'),
            ('1234', 'TEST', 'invalid'),
        ):
            with self.assertRaises(ValueError):
                SIAAccount(account_id, device, partition, KEY)
        self.assertNotIn(repr(KEY), repr(ACCOUNT))

    def test_rejects_unsupported_tokens_structure_timestamp_and_cipher(self):
        for body in (b'"ADM-CID"0001L0#1234[]',
                     b'"SIA-DCS"0001L0#1234[bad]_invalid',
                     b'"SIA-DCS"0001L0#1234[bad][extra]',
                     b'"NULL"0001L0#1234[bad]',
                     b'"SIA-DCS"0001L0#1234[\xff]',
                     b'"*SIA-DCS"0001L0#1234[00'):
            with self.subTest(body=body), self.assertRaises(SIAProtocolError):
                parse_message(frame_body(body), ACCOUNTS)
        with self.assertRaises(SIAProtocolError):
            parse_message(packet(encrypted=True, stamp=None), ACCOUNTS)
        with self.assertRaises(SIAProtocolError):
            parse_message(packet(encrypted=True, key=bytes(16)), ACCOUNTS)
        for cipher in (b'not-hex', b'00', b'0' * 32):
            with self.assertRaises(SIAProtocolError):
                decrypt_content(cipher, KEY)

    def test_fixed_contract_and_explicit_code_mapping(self):
        for code, status, priority in (
            ('BA', 'ACTIVE', 'CRITICAL'), ('BR', 'RESTORED', 'LOW'),
            ('TA', 'TAMPER', 'HIGH'), ('TR', 'RESTORED', 'LOW'),
            ('RP', 'ACTIVE', 'LOW'),
        ):
            message = parse_message(packet(f'#1234|Nri02/{code}003'), ACCOUNTS)
            event = translate_message(message, ACCOUNT, NOW)
            self.assertEqual(
                set(event.model_dump()), set(AlarmEvent.model_fields),
            )
            self.assertEqual((event.sia_code, event.event_status,
                              event.priority_level), (code, status, priority))
            self.assertEqual(event.zone_partition, '02')
            self.assertEqual(event.zone_number, 3)
            self.assertEqual(event.source_type, 'ALARM_PANEL')
            self.assertIsNone(event.correlation_id)
            self.assertEqual(translate_message(message, ACCOUNT, NOW).event_id,
                             event.event_id)
        null = parse_message(packet('', token='NULL', stamp=None), ACCOUNTS)
        self.assertIsNone(translate_message(null, ACCOUNT, NOW))
        message = parse_message(packet('#1234|NBA003', stamp=None), ACCOUNTS)
        event = translate_message(message, ACCOUNT, NOW)
        self.assertEqual(event.timestamp, NOW)
        self.assertEqual(event.zone_partition, '01')
        for data in ('#9999|Nri01/BA003', '#1234|Nri01/XX003'):
            with self.assertRaises(SIAProtocolError):
                translate_message(parse_message(packet(data), ACCOUNTS),
                                  ACCOUNT, NOW)
        ack = parse_message(acknowledge(null, ACCOUNT, NOW), ACCOUNTS)
        with self.assertRaises(SIAProtocolError):
            translate_message(ack, ACCOUNT, NOW)


class ReceiverTests(unittest.IsolatedAsyncioTestCase):
    """Verify acknowledgement order, cache and TCP boundaries."""

    def setUp(self):
        self.publisher = Mock()
        self.clock = 0.0
        self.receiver = SIAReceiver(
            ACCOUNTS, self.publisher, now=lambda: NOW,
            monotonic=lambda: self.clock,
        )

    async def test_publishes_before_ack_and_suppresses_concurrent_retry(self):
        wire = packet(encrypted=True)
        replies = await asyncio.gather(
            self.receiver.process(wire), self.receiver.process(wire),
        )
        self.publisher.publish.assert_called_once()
        self.assertTrue(all(parse_message(reply, ACCOUNTS).token == 'ACK'
                            for reply in replies))
        self.assertEqual(self.publisher.publish.call_args.kwargs['timeout'], 5)
        self.clock = 121
        await self.receiver.process(wire)
        self.assertEqual(self.publisher.publish.call_count, 2)

    async def test_failure_does_not_ack_or_cache_and_retry_is_stable(self):
        self.publisher.publish.side_effect = TimeoutError('synthetic failure')
        with self.assertRaises(TimeoutError):
            await self.receiver.process(packet())
        self.assertEqual(len(self.receiver.seen), 0)
        event_id = self.publisher.publish.call_args.args[0].event_id
        self.publisher.publish.side_effect = None
        await self.receiver.process(packet())
        self.assertEqual(self.publisher.publish.call_args.args[0].event_id,
                         event_id)

    async def test_null_never_publishes_fake_rp(self):
        response = await self.receiver.process(packet('', token='NULL'))
        self.assertEqual(parse_message(response, ACCOUNTS).token, 'ACK')
        self.publisher.publish.assert_not_called()

    async def test_timestamp_and_limits(self):
        for offset in (-21, 21):
            with self.assertRaises(SIAProtocolError):
                await self.receiver.process(packet(
                    stamp=NOW + timedelta(seconds=offset),
                ))
        self.receiver.now = lambda: NOW.replace(tzinfo=None)
        with self.assertRaises(ValueError):
            await self.receiver.process(packet())
        for options in ({'max_frame_bytes': 0}, {'dedup_capacity': 0},
                        {'publish_timeout': 0}):
            with self.assertRaises(ValueError):
                SIAReceiver(ACCOUNTS, self.publisher, **options)
        with self.assertRaises(ValueError):
            SIAReceiver({'wrong': ACCOUNT}, self.publisher)

    async def test_cache_limit_and_sequence_reuse_with_new_content(self):
        self.receiver.dedup_capacity = 1
        await self.receiver.process(packet())
        await self.receiver.process(packet('#1234|Nri01/BR003'))
        self.assertEqual(self.publisher.publish.call_count, 2)
        self.assertEqual(len(self.receiver.seen), 1)

    async def test_tcp_fragmentation_concatenation_and_shutdown(self):
        wire = packet()
        reader = asyncio.StreamReader()
        writer = Mock(wait_closed=AsyncMock(), drain=AsyncMock())
        task = asyncio.create_task(self.receiver.handle_client(reader, writer))
        reader.feed_data(wire[:5])
        await asyncio.sleep(0)
        reader.feed_data(wire[5:] + packet('', token='NULL'))
        reader.feed_eof()
        await task
        self.assertEqual(writer.write.call_count, 2)
        self.assertEqual(len(self.receiver.connections), 0)
        writer.close.assert_called_once()

    async def test_invalid_socket_frame_no_ack_and_safe_log(self):
        for wire in (b'badheader', b'\n00000FFF', packet('#1234|NZZ003')):
            reader = asyncio.StreamReader()
            reader.feed_data(wire)
            reader.feed_eof()
            writer = Mock(wait_closed=AsyncMock(), drain=AsyncMock())
            self.receiver.max_frame_bytes = 100
            with self.assertLogs('backend.integrations.sia_dc09_listener'):
                await self.receiver.handle_client(reader, writer)
            writer.write.assert_not_called()
        self.publisher.publish.assert_not_called()

    async def test_idle_timeout_and_connection_capacity(self):
        self.receiver.read_timeout = 0.001
        writer = Mock(wait_closed=AsyncMock(), drain=AsyncMock())
        with self.assertLogs('backend.integrations.sia_dc09_listener'):
            await self.receiver.handle_client(asyncio.StreamReader(), writer)
        writer.write.assert_not_called()
        self.receiver.max_connections = 1
        self.receiver.connections.add(object())
        writer = Mock(wait_closed=AsyncMock())
        await self.receiver.handle_client(asyncio.StreamReader(), writer)
        writer.close.assert_called_once()
        writer = Mock(
            wait_closed=AsyncMock(side_effect=ConnectionResetError()),
        )
        await self.receiver.handle_client(asyncio.StreamReader(), writer)


SETTINGS = {'account_env': 'TEST_SIA_ACCOUNT', 'device_env': 'TEST_SIA_DEVICE',
            'key_env': 'TEST_SIA_KEY', 'default_partition': '01',
            'allow_plaintext': False}


class StartupTests(unittest.TestCase):
    """Verify secret loading without reading any user's local credentials."""

    def test_env_config_and_invalid_key(self):
        env = {'TEST_SIA_ACCOUNT': '1234', 'TEST_SIA_DEVICE': 'TEST',
               'TEST_SIA_KEY': KEY.hex()}
        with patch.dict(os.environ, env):
            self.assertEqual(account_from_settings(SETTINGS).key, KEY)
            os.environ['TEST_SIA_KEY'] = 'invalid'
            with self.assertRaises(ValueError):
                account_from_settings(SETTINGS)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                account_from_settings(SETTINGS)

    def test_cli_configuration_error_is_safe(self):
        with patch('backend.integrations.sia_dc09_listener.load_settings',
                   return_value={'integrations': {'sia_dc09': SETTINGS}}), \
                patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SystemExit, 'check local settings'):
                main()


class ServeTests(unittest.IsolatedAsyncioTestCase):
    """Verify standalone process lifecycle and resource release."""

    async def test_server_closes_publisher_when_stopped(self):
        server = AsyncMock()
        server.__aenter__.return_value = server
        server.serve_forever.side_effect = asyncio.CancelledError()
        publisher = Mock()
        settings = {'mqtt': {'host': 'localhost', 'port': 1883,
                             'keepalive': 60},
                    'integrations': {'sia_dc09': {
                        'max_frame_bytes': 4095, 'read_timeout_seconds': 10,
                        'max_clock_skew_seconds': 20, 'dedup_seconds': 120,
                        'dedup_capacity': 1024, 'max_connections': 16,
                        'publish_timeout_seconds': 5,
                        'host': '127.0.0.1', 'port': 5500,
                        'supervision': {
                            'enabled': True, 'timeout_seconds': 60,
                            'check_interval_seconds': 1,
                            'account_timeouts': {}, 'heartbeat_mode': 'rp',
                            'publish_timeout_seconds': 5,
                        },
                    }}}
        with patch('backend.integrations.sia_dc09_listener.mqtt.Client') \
                as mqtt_client, patch(
                   'backend.integrations.sia_dc09_listener.EventPublisher',
                   return_value=publisher), patch('asyncio.start_server',
                                                  return_value=server):
            with self.assertRaises(asyncio.CancelledError):
                await serve(settings, ACCOUNT)
        publisher.connect.assert_called_once()
        publisher.close.assert_called_once()
        queue_setter = mqtt_client.return_value.max_queued_messages_set
        queue_setter.assert_called_once_with(128)
