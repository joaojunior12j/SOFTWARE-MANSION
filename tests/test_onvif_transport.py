"""Protocol tests using synthetic camera responses and fragmented TCP reads."""

import hashlib
import os
from pathlib import Path
import struct
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.integrations.onvif_listener import ONVIFCameraConfig
from backend.integrations.onvif_rtp import MetadataRTPAssembler
from backend.integrations.onvif_rtsp import (
    RTSPError, RTSPMetadataSource, control_uri, metadata_track, validate_uri,
)
from backend.integrations.onvif_stream import (
    MetadataSinkError, camera_stream_uri, discover_metadata_uri,
    main, run_metadata_stream,
)


URI = "rtsp://camera.example/stream/"
SDP = (
    'v=0\r\na=control:*\r\nm=video 0 RTP/AVP 96\r\n'
    'a=rtpmap:96 H264/90000\r\na=control:video\r\n'
    'm=application 0 RTP/AVP 107\r\n'
    'a=rtpmap:107 vnd.onvif.metadata/90000\r\na=control:metadata\r\n'
)
FIXTURE = Path(__file__).parent / 'fixtures/onvif_object_metadata.xml'
XML = FIXTURE.read_bytes()
CAMERA = ONVIFCameraConfig('TEST', 'CAMERA-TEST', '01', 3)


def rtp(data, seq=1, marker=True, timestamp=100, ssrc=123, flags=128):
    """Build an RTP packet; values are synthetic."""
    return struct.pack('!BBHII', flags, 107 | (128 if marker else 0),
                       seq, timestamp, ssrc) + data


def interleaved(packet, channel=0):
    """Frame RTP/RTCP bytes as RTSP interleaved binary data."""
    return b'$' + bytes([channel]) + len(packet).to_bytes(2, 'big') + packet


class CameraSocket:
    """Emulate a camera with deterministic RTSP responses and TCP chunks."""

    def __init__(self, auth=False):
        self.data = bytearray()
        self.requests = []
        self.closed = False
        self.auth = auth

    def settimeout(self, timeout):
        pass

    def sendall(self, data):
        request = data.decode()
        self.requests.append(request)
        lines = request.split('\r\n')
        method = lines[0].split()[0]
        cseq = next(line.split(': ', 1)[1] for line in lines
                    if line.startswith('CSeq:'))
        headers = f'CSeq: {cseq}\r\n'
        body = b''
        status = '200 OK'
        if self.auth and 'Authorization:' not in request:
            status = '401 Unauthorized'
            headers += ('WWW-Authenticate: Digest realm="test", '
                        'nonce="synthetic", qop="auth"\r\n')
        elif method == 'DESCRIBE':
            body = SDP.encode()
            headers += f'Content-Base: {URI}\r\n'
        elif method == 'SETUP':
            headers += ('Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\n'
                        'Session: fixture-session;timeout=10\r\n')
        self.data.extend((f'RTSP/1.0 {status}\r\n{headers}'
                          f'Content-Length: {len(body)}\r\n\r\n').encode())
        self.data.extend(body)
        if method == 'PLAY':
            self.data.extend(interleaved(b'rtcp', channel=1))
            self.data.extend(interleaved(rtp(XML[:100], 65535, False)))
            self.data.extend(interleaved(rtp(XML[100:], 0, True, 200)))

    def recv(self, size):
        result = bytes(self.data[:7])
        del self.data[:7]
        return result

    def close(self):
        self.closed = True


class RTPTests(unittest.TestCase):
    """Verify document boundaries, loss handling and memory limits."""

    def test_marker_not_timestamp_closes_document_and_wraps_sequence(self):
        assembler = MetadataRTPAssembler(107, 100)
        self.assertIsNone(assembler.feed(rtp(b'<a>', 65535, False)))
        self.assertEqual(
            assembler.feed(rtp(b'</a>', 0, True, 200)), b'<a></a>',
        )

    def test_loss_and_ssrc_change_drop_until_next_boundary(self):
        for change in ({'seq': 3}, {'seq': 2, 'ssrc': 456}):
            assembler = MetadataRTPAssembler(107, 100)
            assembler.feed(rtp(b'partial', 1, False))
            self.assertIsNone(assembler.feed(rtp(b'broken', **change)))
            self.assertEqual(assembler.feed(rtp(
                b'next', change['seq'] + 1, ssrc=change.get('ssrc', 123),
            )), b'next')

    def test_overflow_discards_document_and_recovers(self):
        assembler = MetadataRTPAssembler(107, 3)
        self.assertIsNone(assembler.feed(rtp(b'oversized')))
        self.assertEqual(assembler.feed(rtp(b'ok', 2)), b'ok')
        self.assertEqual(len(assembler.buffer), 0)

    def test_csrc_extension_and_padding_are_removed(self):
        packet = rtp(b'csrc' + b'\x00\x01\x00\x01' + b'extn'
                     + b'XML' + b'\x00\x02', flags=128 | 1 | 16 | 32)
        self.assertEqual(MetadataRTPAssembler(107, 20).feed(packet), b'XML')

    def test_bad_rtp_headers_are_rejected(self):
        packets = [b'', b'bad', rtp(b'x', flags=64),
                   rtp(b'', flags=129), rtp(b'', flags=144),
                   rtp(b'\0', flags=160), rtp(b'\xff', flags=160)]
        for packet in packets:
            with self.subTest(packet=packet), self.assertRaises(ValueError):
                MetadataRTPAssembler(107, 10).feed(packet)

    def test_other_payload_type_is_ignored_and_limits_validated(self):
        assembler = MetadataRTPAssembler(108, 10)
        self.assertIsNone(assembler.feed(rtp(b'other')))
        for payload, size in [(1, 10), (107, 0)]:
            with self.assertRaises(ValueError):
                MetadataRTPAssembler(payload, size)


class RTSPTests(unittest.TestCase):
    """Verify actual request/response parsing through a fake socket."""

    def test_connect_digest_fragmented_stream_and_teardown(self):
        sock = CameraSocket(auth=True)
        with RTSPMetadataSource(URI, 'fixture-user', 'fixture-secret',
                                connector=lambda *a, **k: sock) as source:
            self.assertEqual(source.keepalive, 5)
            self.assertEqual(next(source.documents(Event())), XML)
            source.request('GET_PARAMETER', URI)
        self.assertTrue(sock.closed)
        self.assertIn('DESCRIBE', sock.requests[0])
        self.assertIn('Authorization: Digest', sock.requests[1])
        self.assertNotIn('fixture-secret', ''.join(sock.requests))
        self.assertIn('TEARDOWN', sock.requests[-1])

    def test_digest_response_hash_for_legacy_and_auth(self):
        source = RTSPMetadataSource(URI, 'user', 'secret')
        source.challenge = 'Digest realm="test", nonce="nonce"'

        def md5(data):
            return hashlib.md5(data.encode()).hexdigest()
        ha1, ha2 = md5('user:test:secret'), md5(f'DESCRIBE:{URI}')
        expected = md5(f'{ha1}:nonce:{ha2}')
        self.assertIn(expected, source._authorization('DESCRIBE', URI))
        source.challenge += ', qop="auth"'
        with patch('secrets.token_hex', return_value='cnonce'):
            expected = md5(f'{ha1}:nonce:00000002:cnonce:auth:{ha2}')
            self.assertIn(expected, source._authorization('DESCRIBE', URI))
        source.challenge += ', algorithm=SHA-256, opaque="opaque"'
        self.assertIn('algorithm=SHA-256', source._authorization('PLAY', URI))
        self.assertIn('opaque="opaque"', source._authorization('PLAY', URI))

    def test_unsupported_auth_never_sends_basic(self):
        source = RTSPMetadataSource(URI, 'user', 'secret')
        for challenge in ('Basic realm="test"', 'Digest realm="test"',
                          'Digest realm="test", nonce="n", qop="auth-int"',
                          'Digest realm="test", nonce="n", algorithm=unknown'):
            source.challenge = challenge
            with self.subTest(challenge=challenge):
                with self.assertRaises(RTSPError):
                    source._authorization('DESCRIBE', URI)

    def test_uri_and_sdp_reject_invalid_or_foreign_endpoints(self):
        for uri in ('http://camera.example/', 'rtsp://u:p@camera.example/',
                    'rtsp://camera.example/\r\nHeader:x', 'rtsp:///',
                    'rtsp://camera.example:99999/',
                    'rtsp://camera.example:0/', 'rtsp://:@camera.example/',
                    'rtsp://camera.example:not-a-port/'):
            with self.subTest(uri=uri):
                with self.assertRaises((RTSPError, ValueError)):
                    validate_uri(uri)
        with self.assertRaises(RTSPError):
            control_uri(URI, 'rtsp://foreign.example/metadata')
        self.assertEqual(
            metadata_track(SDP, URI), (URI + 'metadata', 107, URI),
        )
        for sdp in (
            SDP.replace('vnd.onvif.metadata', 'vnd.onvif.metadata+gzip'),
            SDP.replace('RTP/AVP 107', 'RTP/AVP 108'),
            SDP.replace('a=control:metadata', ''),
        ):
            with self.assertRaises(RTSPError):
                metadata_track(sdp, URI)

    def test_malformed_responses_eof_limits_and_cseq(self):
        for data in (b'RTSP/1.0 200 OK\r\nContent-Length: -1\r\n\r\n',
                     b'HTTP/1.1 200 OK\r\n\r\n',
                     b'RTSP/1.0 200 OK\r\nInvalid\r\n\r\n',
                     b'RTSP/1.0 200 OK\r\nX: a\r\nX: b\r\n\r\n'):
            source = RTSPMetadataSource(URI, 'u', 's')
            source.sock = CameraSocket()
            source.buffer.extend(data)
            with self.assertRaises(RTSPError):
                source._receive_item()
        source.buffer = bytearray()
        with self.assertRaises(EOFError):
            source._receive_item()
        source.sock = Mock()
        source._receive_item = Mock(return_value=SimpleNamespace(
            headers={'cseq': '999'}, status=200,
        ))
        with self.assertRaisesRegex(RTSPError, 'CSeq'):
            source.request('DESCRIBE', URI)

    def test_setup_failure_closes_socket(self):
        sock = CameraSocket()
        source = RTSPMetadataSource(
            URI, 'u', 's', connector=lambda *a, **k: sock,
        )
        with patch.object(source, 'request', side_effect=RTSPError('failure')):
            with self.assertRaises(RTSPError):
                source.__enter__()
        self.assertTrue(sock.closed)
        source.close()
        for value in (0, -1):
            with self.assertRaises(ValueError):
                RTSPMetadataSource(URI, 'u', 's', timeout=value)

    def test_keepalive_and_stop(self):
        sock = CameraSocket()
        with RTSPMetadataSource(URI, 'u', 's',
                                connector=lambda *a, **k: sock) as source:
            source.last_keepalive -= 100
            stream = source.documents(Event())
            self.assertEqual(next(stream), XML)
            self.assertTrue(any('GET_PARAMETER' in r for r in sock.requests))
            stop = Event()
            stop.set()
            self.assertEqual(list(source.documents(stop)), [])


class DiscoveryAndSupervisorTests(unittest.TestCase):
    """Verify read-only profile discovery, safe failures and reconnection."""

    def test_discovers_only_enabled_analytics_profiles(self):
        media = Mock()
        media.GetProfiles.return_value = [
            {'token': 'video', 'MetadataConfiguration': None},
            {'token': 'off', 'MetadataConfiguration': {'Analytics': False}},
            {'token': 'metadata',
             'MetadataConfiguration': {'Analytics': True}},
        ]
        media.GetStreamUri.return_value = {'Uri': URI}
        self.assertEqual(discover_metadata_uri(media), URI)
        request = media.GetStreamUri.call_args.args[0]
        self.assertEqual(request['ProfileToken'], 'metadata')
        self.assertEqual(
            request['StreamSetup']['Transport']['Protocol'], 'RTSP',
        )
        with self.assertRaises(RTSPError):
            discover_metadata_uri(media, 'missing')
        media.GetStreamUri.return_value = {'Uri': None}
        with self.assertRaises(RTSPError):
            discover_metadata_uri(media)

    def test_camera_discovery_has_timeout_and_safe_error(self):
        with patch('onvif.ONVIFCamera') as factory:
            media = factory.return_value.create_media_service.return_value
            media.GetProfiles.return_value = [SimpleNamespace(
                token='metadata', MetadataConfiguration={'Analytics': True},
            )]
            media.GetStreamUri.return_value = {'Uri': URI}
            self.assertEqual(
                camera_stream_uri('camera.example', 80, 'u', 's', 3), URI,
            )
            transport = factory.call_args.kwargs['transport']
            self.assertEqual(transport.operation_timeout, 3)
            factory.side_effect = ValueError('secret server message')
            with self.assertRaisesRegex(RTSPError, 'discovery failed'):
                camera_stream_uri('camera.example', 80, 'u', 's', 3)

    def test_reconnects_and_skips_invalid_xml(self):
        stop = Event()
        source = Mock()
        source.__enter__ = Mock(return_value=source)
        source.__exit__ = Mock(return_value=False)
        source.documents.return_value = iter([b'<broken', XML])
        factory = Mock(side_effect=[OSError('secret'), source])
        received = []

        def callback(item):
            received.append(item)
            if len(received) == 3:
                stop.set()

        with self.assertLogs('backend.integrations.onvif_stream') as logs:
            delivered = run_metadata_stream(
                factory, CAMERA, callback, stop, 1048576, 0.001, 0.002,
            )
        self.assertEqual(delivered, 3)
        self.assertEqual(factory.call_count, 2)
        self.assertNotIn('secret', ''.join(logs.output))
        source.__exit__.assert_called_once()

    def test_callback_failure_stops_instead_of_replaying(self):
        source = Mock()
        source.__enter__ = Mock(return_value=source)
        source.__exit__ = Mock(return_value=False)
        source.documents.return_value = iter([XML])
        sink = Mock(side_effect=ValueError('secret'))
        with self.assertRaises(MetadataSinkError):
            run_metadata_stream(lambda: source, CAMERA, sink, Event(), 1048576)
        sink.assert_called_once()
        with self.assertRaises(ValueError):
            run_metadata_stream(lambda: source, CAMERA, sink, Event(), 0)

    def test_supervisor_stops_during_backoff(self):
        stop = Mock()
        stop.is_set.side_effect = [False, False, False, True]
        factory = Mock(side_effect=OSError('network'))
        with self.assertLogs('backend.integrations.onvif_stream'):
            self.assertEqual(run_metadata_stream(
                factory, CAMERA, Mock(), stop, 100,
            ), 0)
        stop.wait.assert_called_once_with(1)

    def test_stream_cli_uses_environment_and_central_settings(self):
        settings = {'integrations': {'onvif': {
            'stream_timeout_seconds': 5, 'metadata_max_bytes': 1048576,
            'stream_keepalive_seconds': 20, 'reconnect_initial_seconds': 1,
            'reconnect_max_seconds': 30,
        }}}
        args = ['stream', '--account', 'TEST', '--camera-id', 'CAMERA-TEST',
                '--partition', '01', '--zone', '3']
        env = {'ONVIF_CAMERA_HOST': 'camera.example',
               'ONVIF_CAMERA_USERNAME': 'fixture-user',
               'ONVIF_CAMERA_PASSWORD': 'fixture-secret'}

        def interrupted(factory, camera, callback, stop, *limits):
            factory()
            observation = SimpleNamespace(model_dump_json=lambda: '{}')
            callback(observation)
            raise KeyboardInterrupt()

        with patch('sys.argv', args), patch.dict(os.environ, env), patch(
            'backend.integrations.onvif_stream.load_settings',
            return_value=settings,
        ), patch('backend.integrations.onvif_stream.camera_stream_uri',
                 return_value=URI) as discovery, patch(
            'backend.integrations.onvif_stream.run_metadata_stream',
            side_effect=interrupted,
        ), patch('builtins.print') as output:
            main()
        self.assertEqual(discovery.call_args.args[:4], (
            'camera.example', 80, 'fixture-user', 'fixture-secret',
        ))
        output.assert_called_once_with('{}')
        with patch('sys.argv', args), patch.dict(os.environ, {}, clear=True), \
                patch('backend.integrations.onvif_stream.load_settings',
                      return_value=settings), patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                main()
