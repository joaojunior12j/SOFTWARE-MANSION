"""Thread-safe sliding-window foundation for complex event correlation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Protocol
from uuid import UUID, uuid4

from backend.api.schemas import AlarmEvent


class CorrelationRule(Protocol):
    """Contract implemented by correlation rules from Day 9 onward."""

    rule_id: str
    confidence_score: float

    def match(
        self,
        events: Sequence[AlarmEvent],
    ) -> Sequence[AlarmEvent] | None:
        """Return the incident events when this rule matches."""


@dataclass(frozen=True)
class CorrelationResult:
    """One deduced incident with source events linked by a shared UUID."""

    correlation_id: UUID
    rule_triggered: str
    confidence_score: float
    event_ids: tuple[UUID, ...]
    events: tuple[AlarmEvent, ...]
    created_at: datetime


class CorrelationEngine:
    """Buffer canonical events per property and partition in a time window."""

    def __init__(
        self,
        max_window_seconds: float,
        rules: Sequence[CorrelationRule] = (),
        uuid_factory: Callable[[], UUID] = uuid4,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        if max_window_seconds <= 0:
            raise ValueError("max_window_seconds must be positive")
        for rule in rules:
            if not 0.0 <= rule.confidence_score <= 1.0:
                raise ValueError(
                    "rule confidence_score must be between 0 and 1"
                )
        self.max_window_seconds = float(max_window_seconds)
        self.rules = tuple(rules)
        self.uuid_factory = uuid_factory
        self.now_factory = now_factory or (lambda: datetime.now(timezone.utc))
        self._windows: dict[tuple[str, str], list[AlarmEvent]] = {}
        self._latest: dict[tuple[str, str], datetime] = {}
        self._correlated: set[
            tuple[tuple[str, str], str, frozenset[UUID]]
        ] = set()
        self._lock = RLock()

    def process(self, event: AlarmEvent) -> tuple[CorrelationResult, ...]:
        """Add one event, purge expired data, and evaluate registered rules."""
        key = (event.account_id, event.zone_partition)
        with self._lock:
            latest = max(
                event.timestamp,
                self._latest.get(key, event.timestamp),
            )
            self._latest[key] = latest
            window = self._windows.setdefault(key, [])
            window.append(event)
            window.sort(key=lambda item: item.timestamp)
            self._purge_key(key, latest)
            return self._evaluate(key)

    def purge_expired(self, reference_time: datetime) -> int:
        """Remove buffered events older than the window for every zone."""
        if reference_time.tzinfo is None or reference_time.utcoffset() is None:
            raise ValueError("reference_time must include a timezone offset")
        with self._lock:
            return sum(
                self._purge_key(key, reference_time)
                for key in tuple(self._windows)
            )

    def events_for(
        self,
        account_id: str,
        zone_partition: str,
    ) -> tuple[AlarmEvent, ...]:
        """Return an immutable snapshot of one current correlation window."""
        with self._lock:
            return tuple(self._windows.get((account_id, zone_partition), ()))

    def _purge_key(
        self,
        key: tuple[str, str],
        reference_time: datetime,
    ) -> int:
        cutoff = reference_time - timedelta(seconds=self.max_window_seconds)
        current = self._windows.get(key, [])
        retained = [event for event in current if event.timestamp >= cutoff]
        removed = len(current) - len(retained)
        if retained:
            self._windows[key] = retained
        else:
            self._windows.pop(key, None)
            self._latest.pop(key, None)
        retained_ids = {event.event_id for event in retained}
        self._correlated = {
            fingerprint
            for fingerprint in self._correlated
            if fingerprint[0] != key
            or fingerprint[2].issubset(retained_ids)
        }
        return removed

    def _evaluate(
        self,
        key: tuple[str, str],
    ) -> tuple[CorrelationResult, ...]:
        results = []
        for rule in self.rules:
            match = rule.match(tuple(self._windows.get(key, ())))
            if not match:
                continue
            matched = tuple(match)
            buffered_ids = {
                event.event_id for event in self._windows.get(key, ())
            }
            event_ids = tuple(event.event_id for event in matched)
            if not event_ids or not set(event_ids).issubset(buffered_ids):
                raise ValueError(
                    "rule returned events outside its current window"
                )
            fingerprint = (key, rule.rule_id, frozenset(event_ids))
            if fingerprint in self._correlated:
                continue
            self._correlated.add(fingerprint)
            correlation_id = self.uuid_factory()
            linked = tuple(
                event.model_copy(update={"correlation_id": correlation_id})
                for event in matched
            )
            replacements = {event.event_id: event for event in linked}
            self._windows[key] = [
                replacements.get(event.event_id, event)
                for event in self._windows[key]
            ]
            created_at = self.now_factory()
            if created_at.tzinfo is None or created_at.utcoffset() is None:
                raise ValueError("correlation clock must include a timezone")
            results.append(
                CorrelationResult(
                    correlation_id=correlation_id,
                    rule_triggered=rule.rule_id,
                    confidence_score=rule.confidence_score,
                    event_ids=event_ids,
                    events=linked,
                    created_at=created_at,
                )
            )
        return tuple(results)
