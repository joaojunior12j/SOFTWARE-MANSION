"""Bounded SIA DC-09 ASCII framing and AES-CBC for SIA-DCS and ADM-CID.

This is an independent protocol implementation, not a conformance claim for
DC-09-2026. Extended data and key provisioning are unsupported.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
import secrets

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


HEADER = re.compile(
    rb'"(?P<token>\*?(?:SIA-DCS|ADM-CID|NULL|ACK))"(?P<seq>[0-9]{4})'
    rb'(?P<receiver>R[0-9A-Fa-f]{1,6})?(?P<prefix>L[0-9A-Fa-f]{1,6})'
    rb'#(?P<account>[0-9A-Fa-f]{1,16})\[',
)
STAMP = '%H:%M:%S,%m-%d-%Y'


class SIAProtocolError(ValueError):
    """Safe rejection without payloads, keys or device addresses."""


def crc16(data: bytes) -> int:
    """CRC-16/ARC, reflected polynomial 0xA001 and initial value zero."""
    crc = 0
    for octet in data:
        crc ^= octet
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def frame_body(body: bytes) -> bytes:
    """Wrap a body with ASCII CRC, 0LLL length and LF/CR boundaries."""
    if not 0 < len(body) <= 0xFFF or b'\n' in body or b'\r' in body:
        raise SIAProtocolError('invalid DC-09 body length or boundary')
    return f'\n{crc16(body):04X}{len(body):04X}'.encode() + body + b'\r'


def read_body(frame: bytes, max_bytes: int = 4095) -> bytes:
    """Validate boundaries, length and CRC before decoding."""
    if len(frame) < 11 or frame[:1] != b'\n' or frame[-1:] != b'\r':
        raise SIAProtocolError('invalid DC-09 boundaries')
    if not re.fullmatch(rb'[0-9A-Fa-f]{4}0[0-9A-Fa-f]{3}', frame[1:9]):
        raise SIAProtocolError('invalid DC-09 length or CRC encoding')
    body = frame[9:-1]
    if not 0 < len(body) <= max_bytes or int(frame[5:9], 16) != len(body):
        raise SIAProtocolError('DC-09 length mismatch')
    if int(frame[1:5], 16) != crc16(body):
        raise SIAProtocolError('DC-09 CRC mismatch')
    return body


def _cipher(key: bytes):
    if len(key) not in (16, 32):
        raise SIAProtocolError('AES key must have 128 or 256 bits')
    return Cipher(algorithms.AES(key), modes.CBC(bytes(16)))


def encrypt_content(content: bytes, key: bytes) -> bytes:
    """Encrypt random prefix padding, delimiter and content; encode as hex."""
    count = 16 - ((len(content) + 1) % 16)
    # Prefix padding must not contain delimiters used to locate clear content.
    alphabet = bytes(value for value in range(1, 256)
                     if value not in (10, 13, 91, 93, 124))
    padding = bytes(secrets.choice(alphabet) for _ in range(count))
    plain = padding + b'|' + content
    encryptor = _cipher(key).encryptor()
    encrypted = encryptor.update(plain) + encryptor.finalize()
    return encrypted.hex().upper().encode()


def decrypt_content(content: bytes, key: bytes) -> bytes:
    """Remove only DC-09 prefix padding, never PKCS7 or a supplied IV."""
    if not re.fullmatch(rb'(?:[0-9A-Fa-f]{32})+', content):
        raise SIAProtocolError('invalid DC-09 ciphertext')
    decryptor = _cipher(key).decryptor()
    clear = decryptor.update(bytes.fromhex(content.decode()))
    clear += decryptor.finalize()
    boundary = clear.find(b'|')
    if not 1 <= boundary <= 16:
        raise SIAProtocolError('invalid DC-09 encrypted padding')
    return clear[boundary + 1:]


@dataclass(frozen=True)
class SIAMessage:
    """Validated wire message; routing information retained for ACK."""

    token: str
    sequence: str
    receiver: str
    prefix: str
    account: str
    encrypted: bool
    data: str
    timestamp: datetime | None


@dataclass(frozen=True)
class SIAAccount:
    """Provisioned local account; key excluded from repr and loaded via env."""

    account_id: str
    hardware_id: str
    default_partition: str = '01'
    key: bytes | None = field(default=None, repr=False)
    allow_plaintext: bool = False

    def __post_init__(self):
        if not re.fullmatch(r'[0-9A-Fa-f]{1,10}', self.account_id):
            raise ValueError('invalid local SIA account identifier')
        if not self.hardware_id or not re.fullmatch(
            r'[0-9]{1,5}', self.default_partition,
        ):
            raise ValueError('invalid local SIA device metadata')
        if self.key is not None:
            _cipher(self.key)
        if self.key is None and not self.allow_plaintext:
            raise ValueError('SIA account requires an AES key')


def parse_message(frame: bytes, accounts: dict[str, SIAAccount],
                  max_bytes: int = 4095) -> SIAMessage:
    """Validate a known account and decode plaintext or encrypted content."""
    body = read_body(frame, max_bytes)
    header = HEADER.match(body)
    if not header:
        raise SIAProtocolError('unsupported DC-09 message header')
    account_id = header['account'].decode()
    account = accounts.get(account_id)
    if account is None:
        raise SIAProtocolError('unknown SIA account')
    token = header['token'].decode()
    encrypted = token.startswith('*')
    content = body[header.end():]
    if encrypted:
        if account.key is None:
            raise SIAProtocolError('encrypted message has no provisioned key')
        content = decrypt_content(content, account.key)
    elif not account.allow_plaintext:
        raise SIAProtocolError('plaintext disabled for SIA account')
    try:
        text = content.decode('ascii')
    except UnicodeError:
        raise SIAProtocolError('invalid DC-09 content encoding') from None
    match = re.fullmatch(r'(?P<data>[^\[\]\r\n]*)\](?:_(?P<stamp>.+))?', text)
    if not match:
        raise SIAProtocolError('unsupported DC-09 content structure')
    timestamp = None
    if match['stamp']:
        try:
            timestamp = datetime.strptime(match['stamp'], STAMP).replace(
                tzinfo=timezone.utc,
            )
        except ValueError:
            raise SIAProtocolError('invalid DC-09 UTC timestamp') from None
    if encrypted and timestamp is None:
        raise SIAProtocolError('encrypted DC-09 message requires timestamp')
    token = token.lstrip('*')
    if token in ('NULL', 'ACK') and match['data']:
        raise SIAProtocolError('unexpected control message data')
    return SIAMessage(
        token, header['seq'].decode(), (header['receiver'] or b'').decode(),
        header['prefix'].decode(), account_id, encrypted,
        match['data'], timestamp,
    )


def acknowledge(message: SIAMessage, account: SIAAccount,
                now: datetime) -> bytes:
    """Build ACK with original routing and encrypted response when required."""
    token = '*ACK' if message.encrypted else 'ACK'
    header = (f'"{token}"{message.sequence}{message.receiver}'
              f'{message.prefix}#{message.account}[').encode()
    content = b']'
    if message.encrypted:
        stamp = now.astimezone(timezone.utc).strftime(STAMP)
        content += ('_' + stamp).encode()
        content = encrypt_content(content, account.key)
    return frame_body(header + content)
