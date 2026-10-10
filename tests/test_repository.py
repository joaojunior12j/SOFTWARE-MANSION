"""Tests for TimescaleDB event persistence parameters."""

import json
import unittest

from backend.api.schemas import AlarmEvent
from backend.db.repository import EventRepository
from tests.test_event_contract import CANONICAL_EVENT


class FakeConnection:
    """Capture SQL execution without opening a database connection."""

    def __init__(self) -> None:
        self.statement = None
        self.parameters = None

    async def execute(self, statement, parameters) -> None:
        self.statement = statement
        self.parameters = parameters


class FakeTransaction:
    """Async context manager returned by the fake engine."""

    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class FakeEngine:
    """Minimal AsyncEngine substitute used by EventRepository tests."""

    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.disposed = False

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)

    async def dispose(self) -> None:
        self.disposed = True


class RepositoryTests(unittest.TestCase):
    """Verify SQL parameters preserve the complete original event."""

    def test_save_builds_idempotent_insert_parameters(self) -> None:
        engine = FakeEngine()
        repository = EventRepository(engine=engine)
        event = AlarmEvent.model_validate(CANONICAL_EVENT)

        coroutine = repository.save(event, CANONICAL_EVENT)
        with self.assertRaises(StopIteration):
            coroutine.send(None)

        parameters = engine.connection.parameters
        self.assertEqual(parameters["event_id"], CANONICAL_EVENT["event_id"])
        self.assertEqual(parameters["account_id"], "1234")
        self.assertEqual(
            json.loads(parameters["raw_payload"]),
            CANONICAL_EVENT,
        )

    def test_requires_url_or_engine(self) -> None:
        with self.assertRaisesRegex(ValueError, "database_url or engine"):
            EventRepository()

    def test_close_disposes_engine(self) -> None:
        engine = FakeEngine()
        repository = EventRepository(engine=engine)

        coroutine = repository.close()
        with self.assertRaises(StopIteration):
            coroutine.send(None)

        self.assertTrue(engine.disposed)
