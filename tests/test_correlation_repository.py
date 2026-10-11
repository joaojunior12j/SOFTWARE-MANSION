"""Tests for transactional persistence of correlation results."""

from datetime import datetime, timezone
from uuid import UUID
import unittest

from backend.core.correlation_engine import CorrelationResult
from backend.db.correlation_repository import CorrelationRepository
from tests.test_correlation_engine import make_event


class FakeConnection:
    """Capture every SQL execution in order."""

    def __init__(self) -> None:
        self.executions = []

    async def execute(self, statement, parameters) -> None:
        self.executions.append((statement, parameters))


class FakeTransaction:
    """Async transaction context for the fake engine."""

    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class FakeEngine:
    """Minimal async engine substitute."""

    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.disposed = False

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)

    async def dispose(self) -> None:
        self.disposed = True


class CorrelationRepositoryTests(unittest.IsolatedAsyncioTestCase):
    """Verify atomic insert and source-event linking parameters."""

    async def test_save_inserts_then_links_events(self) -> None:
        engine = FakeEngine()
        repository = CorrelationRepository(engine=engine)
        result = CorrelationResult(
            correlation_id=UUID(int=500),
            rule_triggered="TEST_RULE",
            confidence_score=0.95,
            event_ids=(UUID(int=1), UUID(int=2)),
            events=(make_event(1, 0), make_event(2, 1)),
            created_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
        )

        await repository.save(result)

        self.assertEqual(len(engine.connection.executions), 2)
        first_parameters = engine.connection.executions[0][1]
        second_parameters = engine.connection.executions[1][1]
        self.assertIs(first_parameters, second_parameters)
        self.assertEqual(
            first_parameters["correlation_id"],
            str(UUID(int=500)),
        )
        self.assertEqual(
            first_parameters["event_ids"],
            [str(UUID(int=1)), str(UUID(int=2))],
        )

    async def test_shared_engine_is_not_disposed(self) -> None:
        engine = FakeEngine()
        repository = CorrelationRepository(engine=engine)

        await repository.close()

        self.assertFalse(engine.disposed)

    def test_requires_url_or_engine(self) -> None:
        with self.assertRaisesRegex(ValueError, "database_url or engine"):
            CorrelationRepository()
