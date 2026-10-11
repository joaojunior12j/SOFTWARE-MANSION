"""Tests for active-alarm database queries."""

from datetime import datetime, timezone
import unittest
from uuid import UUID

from backend.db.alarm_repository import AlarmRepository
from backend.db.alarm_repository import (
    AlarmNotFoundError,
    InvalidAlarmTransitionError,
)


ALARM_ROW = {
    "alarm_id": UUID("e82fdc9f-5cbb-45ba-88b8-d549941246c8"),
    "correlation_id": None,
    "title": "Intrusão confirmada",
    "description": "Múltiplos sensores",
    "priority_level": "CRITICAL",
    "state": "UNACKNOWLEDGED",
    "zone_partition": "01",
    "triggered_at": datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
    "acknowledged_at": None,
    "acknowledged_by": None,
    "cleared_at": None,
}


class FakeMappings:
    """Return predetermined mapping rows."""

    def all(self):
        return [ALARM_ROW]


class FakeResult:
    """Expose SQLAlchemy's mapping-result shape."""

    def mappings(self):
        return FakeMappings()


class FakeConnection:
    """Capture the active-alarm query."""

    def __init__(self) -> None:
        self.statement = None

    async def execute(self, statement, parameters=None):
        self.statement = statement
        return FakeResult()


class ConnectionContext:
    """Async context manager for the repository fake engine."""

    def __init__(self, connection) -> None:
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *exc_info):
        return None


class FakeEngine:
    """Minimal async engine used by alarm repository tests."""

    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.disposed = False

    def connect(self):
        return ConnectionContext(self.connection)

    def begin(self):
        return ConnectionContext(self.connection)

    async def dispose(self):
        self.disposed = True


class AlarmRepositoryTests(unittest.IsolatedAsyncioTestCase):
    """Verify active-state filtering and response validation."""

    async def test_lists_validated_active_alarms(self) -> None:
        engine = FakeEngine()
        repository = AlarmRepository(engine=engine)

        alarms = await repository.list_active()

        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0].priority_level, "CRITICAL")
        sql = str(engine.connection.statement)
        self.assertIn("state <> 'CLEARED'", sql)
        self.assertIn("WHEN 'CRITICAL' THEN 1", sql)

    async def test_close_disposes_engine(self) -> None:
        engine = FakeEngine()
        repository = AlarmRepository(engine=engine)

        await repository.close()

        self.assertTrue(engine.disposed)

    def test_requires_url_or_engine(self) -> None:
        with self.assertRaises(ValueError):
            AlarmRepository()


class ScalarResult:
    """Return one configured scalar state."""

    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class OneMapping:
    """Return one configured alarm mapping."""

    def __init__(self, row) -> None:
        self.row = row

    def mappings(self):
        return self

    def one(self):
        return self.row


class AcknowledgeConnection:
    """Return lock state followed by the updated alarm row."""

    def __init__(self, state="UNACKNOWLEDGED") -> None:
        self.state = state
        self.executions = []

    async def execute(self, statement, parameters=None):
        self.executions.append((statement, parameters))
        if len(self.executions) == 1:
            return ScalarResult(self.state)
        row = {
            **ALARM_ROW,
            "state": "ACKNOWLEDGED",
            "acknowledged_at": datetime.now(timezone.utc),
            "acknowledged_by": UUID(int=8),
        }
        return OneMapping(row)


class AcknowledgeEngine(FakeEngine):
    """Engine using the acknowledge-aware fake connection."""

    def __init__(self, state="UNACKNOWLEDGED") -> None:
        self.connection = AcknowledgeConnection(state)
        self.disposed = False


class AlarmAcknowledgeRepositoryTests(unittest.IsolatedAsyncioTestCase):
    """Verify the guarded ISA-18.2 acknowledge transition."""

    async def test_acknowledges_unacknowledged_alarm(self) -> None:
        engine = AcknowledgeEngine()
        repository = AlarmRepository(engine=engine)

        alarm = await repository.acknowledge(
            ALARM_ROW["alarm_id"],
            UUID(int=8),
        )

        self.assertEqual(alarm.state, "ACKNOWLEDGED")
        self.assertEqual(alarm.acknowledged_by, UUID(int=8))
        self.assertEqual(len(engine.connection.executions), 2)
        self.assertIn("FOR UPDATE", str(engine.connection.executions[0][0]))

    async def test_rejects_missing_alarm(self) -> None:
        repository = AlarmRepository(engine=AcknowledgeEngine(None))

        with self.assertRaises(AlarmNotFoundError):
            await repository.acknowledge(UUID(int=7), UUID(int=8))

    async def test_rejects_invalid_state_transition(self) -> None:
        repository = AlarmRepository(engine=AcknowledgeEngine("ACKNOWLEDGED"))

        with self.assertRaises(InvalidAlarmTransitionError):
            await repository.acknowledge(UUID(int=7), UUID(int=8))
