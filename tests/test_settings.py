"""Tests for centralized configuration loading."""

import os
from unittest import TestCase
from unittest.mock import Mock, patch

from backend.core.settings import (
    expand_environment,
    load_dotenv,
    load_settings,
)


class SettingsTests(TestCase):
    """Ensure secrets are supplied through the environment."""

    def test_expands_nested_values(self) -> None:
        with patch.dict(os.environ, {"PSIM_TEST_VALUE": "resolved"}):
            result = expand_environment(
                {"database": {"url": "prefix-${PSIM_TEST_VALUE}"}}
            )

        self.assertEqual(result["database"]["url"], "prefix-resolved")

    def test_missing_value_is_an_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "PSIM_MISSING"):
                expand_environment("${PSIM_MISSING}")

    def test_expands_lists_and_preserves_non_strings(self) -> None:
        with patch.dict(os.environ, {"PSIM_ITEM": "value"}):
            result = expand_environment(["${PSIM_ITEM}", 3])

        self.assertEqual(result, ["value", 3])

    def test_load_dotenv_preserves_existing_environment(self) -> None:
        path = Mock()
        path.is_file.return_value = True
        path.read_text.return_value = (
            "# comment\nPSIM_EXISTING=file\nPSIM_NEW=loaded\ninvalid\n"
        )

        with patch.dict(
            os.environ,
            {"PSIM_EXISTING": "environment"},
            clear=True,
        ):
            load_dotenv(path)
            self.assertEqual(os.environ["PSIM_EXISTING"], "environment")
            self.assertEqual(os.environ["PSIM_NEW"], "loaded")

    def test_load_dotenv_ignores_missing_file(self) -> None:
        path = Mock()
        path.is_file.return_value = False

        load_dotenv(path)

        path.read_text.assert_not_called()

    def test_load_settings_reads_yaml_and_resolves_environment(self) -> None:
        config_path = Mock()
        config_path.read_text.return_value = "value: ${PSIM_CONFIG_VALUE}"
        dotenv_path = Mock()
        dotenv_path.is_file.return_value = False

        with patch.dict(os.environ, {"PSIM_CONFIG_VALUE": "resolved"}):
            result = load_settings(config_path, dotenv_path)

        self.assertEqual(result, {"value": "resolved"})

    def test_load_settings_requires_mapping_root(self) -> None:
        config_path = Mock()
        config_path.read_text.return_value = "- item"
        dotenv_path = Mock()
        dotenv_path.is_file.return_value = False

        with self.assertRaisesRegex(ValueError, "mapping"):
            load_settings(config_path, dotenv_path)
