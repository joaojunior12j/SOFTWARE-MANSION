"""Bounded reassembly of uncompressed ONVIF metadata RTP over TCP."""

import struct


class MetadataRTPAssembler:
    """Discard incomplete documents after loss; resume after a marker boundary.

    RTP timestamps may change within one ONVIF XML document. Only the marker
    bit closes a document. This TCP implementation does not reorder UDP.
    """

    def __init__(self, payload_type: int, max_bytes: int) -> None:
        if not 96 <= payload_type <= 127 or max_bytes <= 0:
            raise ValueError("invalid metadata RTP limits")
        self.payload_type = payload_type
        self.max_bytes = max_bytes
        self.buffer = bytearray()
        self.sequence = None
        self.ssrc = None
        self.dropping = False

    def feed(self, packet: bytes) -> bytes | None:
        """Return a complete XML document, or None while buffering/dropping."""
        if len(packet) < 12 or packet[0] >> 6 != 2:
            raise ValueError("invalid RTP header")
        if packet[1] & 127 != self.payload_type:
            return None
        _, _, seq, _, ssrc = struct.unpack("!BBHII", packet[:12])
        offset = 12 + 4 * (packet[0] & 15)
        if packet[0] & 16:
            if len(packet) < offset + 4:
                raise ValueError("truncated RTP extension")
            words = struct.unpack("!H", packet[offset + 2:offset + 4])[0]
            offset += 4 + words * 4
        end = len(packet)
        if packet[0] & 32:
            padding = packet[-1]
            if not padding or padding > end - offset:
                raise ValueError("invalid RTP padding")
            end -= padding
        if offset >= end:
            raise ValueError("empty or truncated RTP payload")
        if self.sequence is not None and (
            seq != (self.sequence + 1) % 65536 or ssrc != self.ssrc
        ):
            self.buffer.clear()
            self.dropping = True
        self.sequence, self.ssrc = seq, ssrc
        marker = bool(packet[1] & 128)
        if not self.dropping:
            if len(self.buffer) + end - offset > self.max_bytes:
                self.buffer.clear()
                self.dropping = True
            else:
                self.buffer.extend(packet[offset:end])
        if not marker:
            return None
        document = None if self.dropping else bytes(self.buffer)
        self.buffer.clear()
        self.dropping = False
        return document
