"""Load central YAML configuration and resolve environment placeholders."""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE entries without overwriting the environment."""
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        os.environ.setdefault(key.strip(), value.strip())


def expand_environment(value: Any) -> Any:
    """Recursively replace ${NAME} placeholders with environment values."""
    if isinstance(value, dict):
        return {key: expand_environment(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_environment(item) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        try:
            return os.environ[name]
        except KeyError as error:
            message = f"missing environment variable: {name}"
            raise ValueError(message) from error

    return ENV_PATTERN.sub(replace, value)


def load_settings(
    config_path: Path | None = None,
    dotenv_path: Path | None = None,
) -> dict[str, Any]:
    """Return the central configuration with environment values resolved."""
    load_dotenv(dotenv_path or PROJECT_ROOT / ".env")
    path = config_path or PROJECT_ROOT / "config" / "config.yaml"
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("config root must be a mapping")
    return expand_environment(parsed)
