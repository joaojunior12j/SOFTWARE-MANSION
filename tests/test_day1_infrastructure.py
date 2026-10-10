"""Static contract tests for the Sprint 1, Day 1 infrastructure."""

from pathlib import Path
import re
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DayOneInfrastructureTests(unittest.TestCase):
    """Guard the fixed event contract and required infrastructure files."""

    def test_required_files_exist(self) -> None:
        required = (
            "docker-compose.yml",
            "config/config.yaml",
            "database/init/001_schema.sql",
            "mosquitto/config/mosquitto.conf",
            ".env.example",
        )

        for relative_path in required:
            with self.subTest(path=relative_path):
                self.assertTrue((PROJECT_ROOT / relative_path).is_file())

    def test_compose_contains_only_day_one_services(self) -> None:
        compose = (PROJECT_ROOT / "docker-compose.yml").read_text(
            encoding="utf-8"
        )

        self.assertRegex(compose, r"(?m)^  mqtt:$")
        self.assertRegex(compose, r"(?m)^  database:$")
        self.assertIn("eclipse-mosquitto:2.0.20", compose)
        self.assertIn("timescale/timescaledb:2.15.3-pg16", compose)
        self.assertNotRegex(compose, r"(?m)^  (api|frontend|simulator):$")

    def test_config_preserves_mqtt_topics_and_windows(self) -> None:
        config = (PROJECT_ROOT / "config/config.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn('events: "mansao/{account_id}/eventos/#"', config)
        self.assertIn(
            'simulator_control: "mansao/{account_id}/simulador/controle"',
            config,
        )
        self.assertRegex(config, r"(?m)^  window_seconds: 60$")
        self.assertRegex(config, r"(?m)^  jammer_window_seconds: 15$")

    def test_schema_contains_every_fixed_payload_field(self) -> None:
        schema = (PROJECT_ROOT / "database/init/001_schema.sql").read_text(
            encoding="utf-8"
        )
        event_table = schema.split(
            "CREATE TABLE IF NOT EXISTS events", maxsplit=1
        )[1]
        event_table = event_table.split(");", maxsplit=1)[0]
        expected_fields = (
            "event_id",
            "timestamp",
            "account_id",
            "source_type",
            "device_hardware_id",
            "zone_partition",
            "zone_number",
            "sia_code",
            "event_status",
            "priority_level",
            "correlation_id",
        )

        for field in expected_fields:
            with self.subTest(field=field):
                self.assertRegex(event_table, rf"(?m)^\s+{re.escape(field)}\s")

    def test_schema_creates_timescale_hypertable_idempotently(self) -> None:
        schema = (PROJECT_ROOT / "database/init/001_schema.sql").read_text(
            encoding="utf-8"
        )

        self.assertIn("CREATE EXTENSION IF NOT EXISTS timescaledb", schema)
        self.assertIn("SELECT create_hypertable(", schema)
        self.assertIn("if_not_exists => TRUE", schema)
        self.assertIn("PRIMARY KEY (event_id, timestamp)", schema)


if __name__ == "__main__":
    unittest.main()
