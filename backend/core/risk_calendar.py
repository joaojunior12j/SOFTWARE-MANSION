"""Local civil-time risk policy, independent of physical sensor control."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class RiskState:
    """One evaluated policy snapshot; this is not a canonical alarm event."""

    mode: str
    reason: str
    timezone: str
    evaluated_at: datetime
    local_time: datetime
    pir_alpha_multiplier: float
    scope: str = 'SIMULATOR_PIR'


class RiskCalendar:
    """Match configured local hours/dates without stacking boosts."""

    def __init__(self, config: Mapping):
        allowed = {'enabled', 'timezone', 'pir_alpha_multiplier',
                   'high_risk_times', 'high_risk_holidays'}
        if not isinstance(config, Mapping) or set(config) - allowed:
            raise ValueError('invalid risk calendar configuration')
        self.enabled = config.get('enabled', True)
        if not isinstance(self.enabled, bool):
            raise ValueError('risk enabled must be boolean')
        self.timezone_name = config.get('timezone', 'America/Sao_Paulo')
        try:
            self.zone = ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, TypeError, ValueError):
            raise ValueError('risk timezone must be an available IANA zone')
        factor = config.get('pir_alpha_multiplier', 1.5)
        if (isinstance(factor, bool) or not isinstance(factor, (int, float))
                or not math.isfinite(factor) or not 1 <= factor <= 3):
            raise ValueError('risk PIR alpha multiplier must be within 1..3')
        self.multiplier = float(factor)
        hours = config.get('high_risk_times', [])
        holidays = config.get('high_risk_holidays', [])
        if not isinstance(hours, list) or not isinstance(holidays, list):
            raise ValueError('risk hours and dates must be lists')
        selected = set()
        for item in hours:
            if (not isinstance(item, Mapping)
                    or set(item) != {'weekday', 'hour'}
                    or type(item['weekday']) is not int
                    or type(item['hour']) is not int
                    or not 0 <= item['weekday'] <= 6
                    or not 0 <= item['hour'] <= 23):
                raise ValueError('invalid risk weekday/hour')
            selected.add((item['weekday'], item['hour']))
        dates = set()
        for item in holidays:
            try:
                if not isinstance(item, str):
                    raise ValueError
                parsed = date.fromisoformat(item)
                if parsed.isoformat() != item:
                    raise ValueError
                dates.add(parsed)
            except ValueError:
                raise ValueError('risk dates must use valid YYYY-MM-DD')
        self.hours = frozenset(selected)
        self.dates = frozenset(dates)

    @classmethod
    def from_settings(cls, settings: Mapping) -> 'RiskCalendar':
        """Missing block preserves the pre-calendar sensor behavior."""
        return cls(settings.get('risk_calendar', {'enabled': False}))

    def evaluate(self, instant: datetime | None = None) -> RiskState:
        """Use an aware instant; local hour/date matching handles DST folds."""
        if instant is None:
            instant = datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError('risk clock must include a timezone')
        local = instant.astimezone(self.zone)
        mode, reason = 'STANDARD', 'outside_schedule'
        if not self.enabled:
            mode, reason = 'DISABLED', 'disabled'
        elif local.date() in self.dates:
            mode, reason = 'ELEVATED', 'configured_date'
        elif (local.weekday(), local.hour) in self.hours:
            mode, reason = 'ELEVATED', 'weekly_hour'
        return RiskState(
            mode, reason, self.timezone_name,
            instant.astimezone(timezone.utc), local,
            self.multiplier if mode == 'ELEVATED' else 1.0,
        )
