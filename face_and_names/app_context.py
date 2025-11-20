"""
Application bootstrap helpers.

Responsibilities:
- Locate/load configuration.
- Resolve database path and initialize the schema.
- Configure logging layout tied to the DB root.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from face_and_names.config.loader import load_config
from face_and_names.logging.setup import setup_logging
from face_and_names.models.db import initialize_database

ENV_CONFIG_DIR = "FACE_AND_NAMES_CONFIG_DIR"
ENV_DB_PATH = "FACE_AND_NAMES_DB_PATH"


@dataclass
class AppContext:
    """Shared application context passed into the UI."""

    config: dict[str, Any]
    db_path: Path
    conn: sqlite3.Connection


def default_config_dir() -> Path:
    """Return the directory to hold config files, honoring env override."""
    override = os.getenv(ENV_CONFIG_DIR)
    if override:
        return Path(override)
    return Path.home() / ".face_and_names"


def default_config_path() -> Path:
    """Return default config file path."""
    return default_config_dir() / "config.toml"


def resolve_db_path(config: dict[str, Any], base_dir: Path | None = None) -> Path:
    """
    Determine the database path using env override, config, and base_dir.
    Relative paths resolve against base_dir or CWD.
    """
    override = os.getenv(ENV_DB_PATH)
    db_path = Path(override) if override else Path(config.get("db", {}).get("path", "faces.db"))
    root = base_dir or Path.cwd()
    return db_path if db_path.is_absolute() else root / db_path


def initialize_app(
    config_path: Path | None = None, db_path: Path | None = None, base_dir: Path | None = None
) -> AppContext:
    """
    Load configuration, set up logging, initialize the database schema, and return an AppContext.
    """
    config_path = config_path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)

    resolved_db_path = db_path or resolve_db_path(config, base_dir=base_dir)
    conn = initialize_database(resolved_db_path)

    log_dir = resolved_db_path.parent / "logs"
    setup_logging(log_dir=log_dir, level=str(config.get("logging", {}).get("level", "INFO")))

    return AppContext(config=config, db_path=resolved_db_path, conn=conn)
