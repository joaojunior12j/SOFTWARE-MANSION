"""RTSP 1.0 client for uncompressed ONVIF metadata over interleaved TCP.

Supports Digest MD5/SHA-256 with qop=auth or legacy no-qop. Does not follow
redirects, send Basic credentials, or negotiate compressed/UDP media.
"""

from collections import deque
from dataclasses import dataclass
import hashlib
import re
import secrets
import socket
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import parse_http_list, parse_keqv_list

from backend.integrations.onvif_rtp import MetadataRTPAssembler


class RTSPError(Exception):
    """Protocol failure with a safe message and no server content."""


def validate_uri(uri: str) -> None:
    """Reject URI credentials and control characters before requests."""
    try:
        parts = urlsplit(uri)
        port = 554 if parts.port is None else parts.port
    except ValueError:
        raise RTSPError("invalid RTSP URI") from None
    if (parts.scheme != "rtsp" or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.fragment
            or any(ord(char) <= 32 or ord(char) == 127 for char in uri)):
        raise RTSPError("expected credential-free RTSP URI")
    if not 0 < port <= 65535:
        raise RTSPError("invalid RTSP port")


def control_uri(base: str, control: str) -> str:
    """Resolve SDP controls without sending credentials to another origin."""
    target = urljoin(base, control)
    validate_uri(target)
    old, new = urlsplit(base), urlsplit(target)
    if (old.hostname, old.port or 554) != (new.hostname, new.port or 554):
        raise RTSPError("cross-origin RTSP control is unsupported")
    return target


def metadata_track(sdp: str, base: str) -> tuple[str, int, str]:
    """Choose only an application track with ONVIF XML at 90 kHz."""
    session_control = base
    sections = []
    section = None
    for line in sdp.splitlines():
        line = line.strip()
        if line.startswith("m="):
            section = {"media": line[2:].split(), "control": None, "map": {}}
            sections.append(section)
        elif line.startswith("a=control:"):
            value = line.split(":", 1)[1]
            if section is None:
                session_control = base if value == "*" else control_uri(
                    base, value,
                )
            else:
                section["control"] = value
        elif line.startswith("a=rtpmap:") and section is not None:
            fields = line[9:].split()
            if len(fields) == 2:
                section["map"][fields[0]] = fields[1].lower()
    for section in sections:
        media = section["media"]
        if len(media) < 4 or media[0] != "application":
            continue
        if media[2] != "RTP/AVP" or not section["control"]:
            continue
        for payload in media[3:]:
            if section["map"].get(payload) == "vnd.onvif.metadata/90000":
                value = int(payload)
                if 96 <= value <= 127:
                    return (
                        control_uri(base, section["control"]), value,
                        session_control,
                    )
    raise RTSPError("no supported uncompressed ONVIF metadata track")


@dataclass
class Response:
    """Parsed RTSP response, never included in user-visible errors."""

    status: int
    headers: dict
    body: bytes


class RTSPMetadataSource:
    """One RTSP session; yields reconstructed XML documents to a listener."""

    def __init__(self, uri, username, password, timeout=5,
                 max_bytes=1048576, keepalive=20, connector=None):
        validate_uri(uri)
        if timeout <= 0 or max_bytes <= 0 or keepalive <= 0:
            raise ValueError("RTSP limits must be positive")
        self.uri = uri
        self.username = username
        self.password = password
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.keepalive = keepalive
        self.connector = connector or socket.create_connection
        self.sock = None
        self.buffer = bytearray()
        self.pending = deque()
        self.cseq = 0
        self.session = None
        self.challenge = None
        self.nonce_count = 0
        self.assembler = None
        self.channel = None
        self.aggregate = uri

    def _authorization(self, method, uri):
        challenge = self.challenge
        if challenge is None:
            return None
        if challenge[:7].lower() != "digest ":
            raise RTSPError("RTSP requires unsupported authentication")
        values = parse_keqv_list(parse_http_list(challenge[7:]))
        algorithm = values.get("algorithm", "MD5").upper()
        hashes = {"MD5": hashlib.md5, "SHA-256": hashlib.sha256}
        hash_fn = hashes.get(algorithm)
        if not hash_fn or not values.get("realm") or not values.get("nonce"):
            raise RTSPError("unsupported Digest challenge")
        qop = values.get("qop")
        if qop and "auth" not in [item.strip() for item in qop.split(",")]:
            raise RTSPError("unsupported Digest qop")
        realm, nonce = values["realm"], values["nonce"]
        self.nonce_count += 1
        nc, cnonce = f"{self.nonce_count:08x}", secrets.token_hex(16)

        def digest(value):
            return hash_fn(value.encode("utf-8")).hexdigest()

        ha1 = digest(f"{self.username}:{realm}:{self.password}")
        ha2 = digest(f"{method}:{uri}")
        response = digest(
            f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}" if qop
            else f"{ha1}:{nonce}:{ha2}"
        )

        def quoted(value):
            if any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise RTSPError("invalid Digest field")
            return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'

        result = (
            f"Digest username={quoted(self.username)}, realm={quoted(realm)}, "
            f"nonce={quoted(nonce)}, uri={quoted(uri)}, "
            f"response={quoted(response)}, algorithm={algorithm}"
        )
        if qop:
            result += f", qop=auth, nc={nc}, cnonce={quoted(cnonce)}"
        if "opaque" in values:
            result += f", opaque={quoted(values['opaque'])}"
        return result

    def _receive_item(self):
        """Read a bounded RTSP response or interleaved frame incrementally."""
        deadline = time.monotonic() + self.timeout
        while True:
            if self.buffer[:1] == b"$" and len(self.buffer) >= 4:
                size = int.from_bytes(self.buffer[2:4], "big")
                if len(self.buffer) >= size + 4:
                    channel = self.buffer[1]
                    payload = bytes(self.buffer[4:size + 4])
                    del self.buffer[:size + 4]
                    return channel, payload
            elif self.buffer[:1] != b"$":
                end = self.buffer.find(b"\r\n\r\n")
                if end > 65536:
                    raise RTSPError("RTSP headers exceed limit")
                if end >= 0:
                    try:
                        lines = self.buffer[:end].decode("utf-8").split("\r\n")
                        version, status, _ = lines[0].split(" ", 2)
                        if version != "RTSP/1.0":
                            raise ValueError()
                        headers = {}
                        for line in lines[1:]:
                            name, value = line.split(":", 1)
                            name = name.lower()
                            if name in headers:
                                raise ValueError()
                            headers[name] = value.strip()
                        size = int(headers.get("content-length", "0"))
                        if not 0 <= size <= self.max_bytes:
                            raise ValueError()
                    except (ValueError, UnicodeError):
                        raise RTSPError("invalid RTSP response") from None
                    if len(self.buffer) >= end + 4 + size:
                        body = bytes(self.buffer[end + 4:end + 4 + size])
                        del self.buffer[:end + 4 + size]
                        return Response(int(status), headers, body)
                elif len(self.buffer) > 65536:
                    raise RTSPError("RTSP headers exceed limit")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("RTSP read timed out")
            self.sock.settimeout(remaining)
            data = self.sock.recv(4096)
            if not data:
                raise EOFError("RTSP connection closed")
            self.buffer.extend(data)

    def _frame(self, item):
        channel, packet = item
        if self.assembler is not None and channel == self.channel:
            document = self.assembler.feed(packet)
            if document is not None:
                # Bound documents queued while waiting for RTSP responses.
                if len(self.pending) >= 4:
                    raise RTSPError("RTSP metadata queue overflow")
                self.pending.append(document)

    def request(self, method, uri, headers=None):
        """Correlate responses and perform at most one Digest retry."""
        for attempt in range(2):
            self.cseq += 1
            fields = {"CSeq": str(self.cseq), **(headers or {})}
            if self.session:
                fields["Session"] = self.session
            authorization = self._authorization(method, uri)
            if authorization:
                fields["Authorization"] = authorization
            lines = [f"{method} {uri} RTSP/1.0"]
            for key, value in fields.items():
                if "\r" in value or "\n" in value:
                    raise RTSPError("invalid RTSP header")
                lines.append(f"{key}: {value}")
            self.sock.settimeout(self.timeout)
            self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
            deadline = time.monotonic() + self.timeout
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError("RTSP response timed out")
                item = self._receive_item()
                if isinstance(item, tuple):
                    self._frame(item)
                    continue
                if item.headers.get("cseq") != str(self.cseq):
                    raise RTSPError("RTSP CSeq mismatch")
                break
            if item.status == 401 and attempt == 0:
                self.challenge = item.headers.get("www-authenticate", "")
                self.nonce_count = 0
                continue
            if item.status != 200:
                raise RTSPError(f"RTSP request rejected ({item.status})")
            return item
        raise RTSPError("RTSP authentication failed")

    def __enter__(self):
        parts = urlsplit(self.uri)
        try:
            self.sock = self.connector(
                (parts.hostname, parts.port or 554), timeout=self.timeout,
            )
            described = self.request("DESCRIBE", self.uri, {
                "Accept": "application/sdp",
            })
            base = described.headers.get("content-base", self.uri)
            control_uri(self.uri, base)
            track, payload, self.aggregate = metadata_track(
                described.body.decode("utf-8"), base,
            )
            setup = self.request("SETUP", track, {
                "Transport": "RTP/AVP/TCP;unicast;interleaved=0-1",
            })
            transport = setup.headers.get("transport", "")
            channels = re.search(r"interleaved=(\d+)-(\d+)", transport)
            if (not transport.startswith("RTP/AVP/TCP") or not channels
                    or int(channels[2]) != int(channels[1]) + 1
                    or int(channels[2]) > 255):
                raise RTSPError("unsupported negotiated RTSP transport")
            self.channel = int(channels[1])
            session = setup.headers.get("session", "")
            self.session = session.split(";", 1)[0]
            if not self.session:
                raise RTSPError("missing RTSP session")
            timeout = re.search(r"timeout=(\d+)", session)
            if timeout:
                if int(timeout[1]) < 2:
                    raise RTSPError("invalid RTSP session timeout")
                self.keepalive = min(self.keepalive, int(timeout[1]) / 2)
            self.assembler = MetadataRTPAssembler(payload, self.max_bytes)
            self.request("PLAY", self.aggregate)
            self.last_keepalive = time.monotonic()
            return self
        except Exception:
            self.close()
            raise

    def documents(self, stop):
        """Yield XML with bounded reads and reconnect on inactivity."""
        while not stop.is_set():
            if time.monotonic() - self.last_keepalive >= self.keepalive:
                self.request("GET_PARAMETER", self.aggregate)
                self.last_keepalive = time.monotonic()
            if self.pending:
                yield self.pending.popleft()
                continue
            item = self._receive_item()
            if not isinstance(item, tuple):
                raise RTSPError("unsolicited RTSP response")
            self._frame(item)

    def close(self):
        """Release the connection even if setup/play or teardown failed."""
        if self.sock is not None:
            try:
                if self.session:
                    self.request("TEARDOWN", self.aggregate)
            except (OSError, EOFError, ValueError, RTSPError):
                pass
            finally:
                self.sock.close()
                self.sock = None

    def __exit__(self, *exc_info):
        self.close()
