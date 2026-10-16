"""Per-account SIA supervision with bounded transition retries."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import math
import time
from uuid import uuid4

from backend.api.schemas import AlarmEvent


LOGGER = logging.getLogger(__name__)


@dataclass
class AccountState:
    """At most two pending transitions per provisioned account."""

    last_seen: float
    wire_time: datetime | None = None
    untimed_identity: tuple | None = None
    reported_lost: bool = False
    pending_loss: AlarmEvent | None = None
    pending_return: AlarmEvent | None = None


class SIACommunicationSupervisor:
    """Monitor accepted RP (default) or any supported validated SIA message.

    The receiver shares the lock across message acceptance and checks.
    State is volatile. MQTT retries retain the original event UUID.
    """

    def __init__(self, accounts, publisher, timeout_seconds=60,
                 check_interval=1, account_timeouts=None, heartbeat_mode='rp',
                 publish_timeout=5, now=None, monotonic=None):
        account_timeouts = account_timeouts or {}
        if not accounts or set(account_timeouts) - set(accounts):
            raise ValueError('invalid SIA supervision account registry')
        limits = [timeout_seconds, check_interval, publish_timeout,
                  *account_timeouts.values()]
        if any(not math.isfinite(value) or value <= 0 for value in limits):
            raise ValueError('SIA intervals must be positive and finite')
        if heartbeat_mode not in ('rp', 'any_valid_message'):
            raise ValueError('unsupported SIA heartbeat policy')
        self.accounts = dict(accounts)
        self.publisher = publisher
        self.timeouts = {
            key: account_timeouts.get(key, timeout_seconds) for key in accounts
        }
        if check_interval > min(self.timeouts.values()):
            raise ValueError('SIA check interval exceeds account timeout')
        self.check_interval = check_interval
        self.heartbeat_mode = heartbeat_mode
        self.publish_timeout = publish_timeout
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        started = self.monotonic()
        self.states = {key: AccountState(started) for key in accounts}
        self.lock = asyncio.Lock()

    def _event(self, account_id, status, timestamp):
        account = self.accounts[account_id]
        return AlarmEvent(
            event_id=uuid4(), timestamp=timestamp,
            account_id=account.account_id, source_type='ALARM_PANEL',
            device_hardware_id=account.hardware_id,
            zone_partition=account.default_partition, zone_number=0,
            sia_code='RP', event_status=status,
            priority_level='HIGH' if status == 'TIMEOUT_SIA_DC09' else 'LOW',
            correlation_id=None,
        )

    def observe(self, message, event, received_at):
        """Accept a fresh heartbeat while the shared lock is held.

        Called only after the receiver's publication succeeds (or valid NULL).
        Old timestamps and retransmissions do not renew supervision.
        """
        if self.heartbeat_mode == 'rp' and (
            event is None or event.sia_code != 'RP'
        ):
            return False
        state = self.states[message.account]
        if message.timestamp is not None:
            if (state.wire_time is not None
                    and message.timestamp <= state.wire_time):
                return False
            state.wire_time = message.timestamp
        else:
            identity = (message.token, message.sequence, message.data)
            if identity == state.untimed_identity:
                return False
            state.untimed_identity = identity
        state.last_seen = self.monotonic()
        lost = state.reported_lost or state.pending_loss is not None
        if lost and state.pending_return is None:
            state.pending_return = self._event(
                message.account, 'RESTORED', received_at,
            )
        return True

    async def check_once(self):
        """Publish transitions; failed attempts retain their UUID."""
        count = 0
        async with self.lock:
            clock = self.monotonic()
            for account_id, state in self.states.items():
                if (not state.reported_lost and state.pending_loss is None
                        and state.pending_return is None
                        and clock - state.last_seen
                        >= self.timeouts[account_id]):
                    state.pending_loss = self._event(
                        account_id, 'TIMEOUT_SIA_DC09', self.now(),
                    )
                try:
                    if state.pending_loss is not None:
                        await asyncio.to_thread(
                            self.publisher.publish, state.pending_loss,
                            timeout=self.publish_timeout,
                        )
                        state.pending_loss = None
                        state.reported_lost = True
                        count += 1
                    if state.pending_return is not None:
                        await asyncio.to_thread(
                            self.publisher.publish, state.pending_return,
                            timeout=self.publish_timeout,
                        )
                        state.pending_return = None
                        state.reported_lost = False
                        count += 1
                except (OSError, RuntimeError, ValueError):
                    LOGGER.warning('SIA supervision publish failed; retrying')
        return count

    async def run(self):
        """Check provisioned accounts until task cancellation."""
        while True:
            await self.check_once()
            await asyncio.sleep(self.check_interval)


def supervisor_from_settings(settings, accounts, publisher):
    """Build the explicitly configured policy, or disable supervision."""
    if not settings['enabled']:
        return None
    return SIACommunicationSupervisor(
        accounts, publisher, settings['timeout_seconds'],
        settings['check_interval_seconds'], settings['account_timeouts'],
        settings['heartbeat_mode'], settings['publish_timeout_seconds'],
    )
