"""Real loopback RTSP socket smoke using a synthetic camera, plus MQTT."""

import hashlib
import socketserver
from threading import Event, Thread
from urllib.request import parse_http_list, parse_keqv_list

from backend.integrations.onvif_rtsp import RTSPMetadataSource
from backend.integrations.onvif_stream import run_metadata_stream
from tests.smoke_day11 import run as mqtt_smoke
from tests.test_onvif_transport import CAMERA, CameraSocket, SDP


class FixtureServer(socketserver.TCPServer):
    """Loopback-only synthetic camera recording its method sequence."""

    allow_reuse_address = True

    def __init__(self):
        self.methods = []
        self.errors = []
        super().__init__(('127.0.0.1', 0), FixtureHandler)


class FixtureHandler(socketserver.BaseRequestHandler):
    """Respond to real RTSP requests with deterministic metadata packets."""

    def handle(self):
        self.request.settimeout(5)
        buffered = bytearray()
        camera = CameraSocket(auth=True)
        try:
            while True:
                chunk = self.request.recv(4096)
                if not chunk:
                    break
                buffered.extend(chunk)
                while b'\r\n\r\n' in buffered:
                    end = buffered.index(b'\r\n\r\n') + 4
                    request = bytes(buffered[:end])
                    del buffered[:end]
                    method = request.split(b' ', 1)[0].decode()
                    self.server.methods.append(method)
                    authorization = next((
                        line[22:].strip()
                        for line in request.decode().splitlines()
                        if line.startswith('Authorization: Digest ')
                    ), None)
                    if authorization is not None:
                        values = parse_keqv_list(
                            parse_http_list(authorization),
                        )

                        def digest(value):
                            return hashlib.md5(value.encode()).hexdigest()

                        ha1 = digest('fixture-user:test:fixture-secret')
                        ha2 = digest(f"{method}:{values['uri']}")
                        expected = digest(
                            f"{ha1}:synthetic:{values['nc']}:"
                            f"{values['cnonce']}:auth:{ha2}"
                        )
                        if values['response'] != expected:
                            raise RuntimeError('invalid Digest response')
                    camera.sendall(request)
                    data = bytes(camera.data)
                    camera.data.clear()
                    # Resolve fake Content-Base against this actual loopback
                    # endpoint while keeping all media/RTP bytes unchanged.
                    origin = self.server.origin.encode()
                    data = data.replace(
                        b'rtsp://camera.example/stream/', origin,
                    )
                    # SDP relative tracks intentionally survive resolution.
                    if method == 'DESCRIBE' and b'200 OK' in data:
                        assert SDP.encode() in data
                    for offset in range(0, len(data), 13):
                        self.request.sendall(data[offset:offset + 13])
                    if method == 'TEARDOWN':
                        return
        except Exception as error:
            self.server.errors.append(type(error).__name__)


def run():
    """Receive classifications through RTSP/Digest/TCP/RTP/XML on loopback."""
    with FixtureServer() as server:
        server.origin = f'rtsp://127.0.0.1:{server.server_address[1]}/stream/'
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        stop = Event()
        received = []

        def callback(observation):
            received.append(observation)
            if len(received) == 3:
                stop.set()

        def source():
            return RTSPMetadataSource(
                server.origin, 'fixture-user', 'fixture-secret', timeout=3,
            )

        watchdog = Thread(
            target=lambda: (stop.wait(10), stop.set()), daemon=True,
        )
        watchdog.start()
        try:
            delivered = run_metadata_stream(
                source, CAMERA, callback, stop, 1048576, 0.01, 0.02,
            )
        finally:
            stop.set()
            server.shutdown()
            thread.join(3)
        if delivered != 3 or server.errors:
            raise RuntimeError('loopback RTSP metadata smoke failed')
        if [item.classes[0].label for item in received] != [
            'Human', 'Vehicle', 'Vehicle',
        ]:
            raise RuntimeError('unexpected RTSP classifications')
        if server.methods != [
            'DESCRIBE', 'DESCRIBE', 'SETUP', 'PLAY', 'TEARDOWN',
        ]:
            raise RuntimeError('unexpected RTSP session lifecycle')
    mqtt_smoke()
    print('rtsp_digest=ok tcp_rtp_xml=ok classification=ok teardown=ok')


if __name__ == '__main__':
    run()
