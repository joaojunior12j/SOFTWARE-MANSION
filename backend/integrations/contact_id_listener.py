"""Contact ID intrusion subset over the shared DC-09 TCP receiver.

No telephone DTMF decoding or proprietary raw TCP transport is implemented.
"""

from datetime import datetime
import re
from uuid import NAMESPACE_URL, uuid4, uuid5

from backend.api.schemas import AlarmEvent
from backend.integrations.sia_dc09 import (
    SIAAccount, SIAMessage, SIAProtocolError,
)


CONTACT_ID = re.compile(
    r'#(?P<account>[0-9A-Fa-f]{1,16})\|(?P<qualifier>[13])'
    r'(?P<code>130|137|602) (?P<partition>[0-9]{2}) (?P<zone>[0-9]{3})',
)
POLICY = {
    ('1', '130'): ('BA', 'ACTIVE', 'CRITICAL'),
    ('3', '130'): ('BR', 'RESTORED', 'LOW'),
    ('1', '137'): ('TA', 'TAMPER', 'HIGH'),
    ('3', '137'): ('TR', 'RESTORED', 'LOW'),
    ('1', '602'): ('RP', 'ACTIVE', 'LOW'),
}


def translate_contact_id(message: SIAMessage, account: SIAAccount,
                         received_at: datetime) -> AlarmEvent:
    """Normalize supported ADM-CID codes without inventing zone devices."""
    match = CONTACT_ID.fullmatch(message.data)
    if (message.token != 'ADM-CID' or not match
            or match['account'] != message.account
            or message.account != account.account_id):
        raise SIAProtocolError('unsupported Contact ID event or account')
    policy = POLICY.get((match['qualifier'], match['code']))
    if policy is None:
        raise SIAProtocolError('unsupported Contact ID qualifier')
    code, status, priority = policy
    event_id = uuid4()
    if message.timestamp is not None:
        identity = (message.account, message.sequence,
                    message.timestamp.isoformat(), message.data)
        event_id = uuid5(NAMESPACE_URL, 'psim:adm-cid:' + repr(identity))
    return AlarmEvent(
        event_id=event_id, timestamp=message.timestamp or received_at,
        account_id=account.account_id, source_type='ALARM_PANEL',
        device_hardware_id=account.hardware_id,
        zone_partition=match['partition'], zone_number=int(match['zone']),
        sia_code=code, event_status=status, priority_level=priority,
        correlation_id=None,
    )


def main():
    """Run the shared listener; this alias does not open a second socket."""
    from backend.integrations.sia_dc09_listener import main as run
    run()


if __name__ == '__main__':
    main()
