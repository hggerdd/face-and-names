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
from face_and_names.services.people_service import PeopleService
from face_and_names.services.person_registry import default_registry_path
from face_and_names.services.prediction_service import PredictionService
from face_and_names.services.workers import JobManager
from face_and_names.utils.event_bus import EventBus

ENV_CONFIG_DIR = "FACE_AND_NAMES_CONFIG_DIR"
ENV_DB_PATH = "FACE_AND_NAMES_DB_PATH"


@dataclass
class AppContext:
    """Shared application context passed into the UI."""

    config: dict[str, Any]
    config_path: Path
    db_path: Path
    conn: sqlite3.Connection
    job_manager: JobManager
    events: EventBus
    people_service: PeopleService
    registry_path: Path
    prediction_service: PredictionService | None


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
    config_dir = config_path.parent
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)

    last_db = load_last_db_path(config_dir)
    resolved_db_path = db_path or last_db or resolve_db_path(config, base_dir=base_dir)
    conn = initialize_database(resolved_db_path)

    log_dir = resolved_db_path.parent / "logs"
    setup_logging(log_dir=log_dir, level=str(config.get("logging", {}).get("level", "INFO")))

    worker_cfg = config.get("workers", {}) if isinstance(config, dict) else {}
    job_manager = JobManager(max_workers=int(worker_cfg.get("cpu_max", 2)))
    events = EventBus()
    registry_path = default_registry_path(base_dir or Path.cwd())
    people_service = PeopleService(conn, registry_path=registry_path)
    prediction_service: PredictionService | None = None
    try:
        prediction_service = PredictionService(model_dir=Path("model"))
    except Exception:
        prediction_service = None

    return AppContext(
        config=config,
        config_path=config_path,
        db_path=resolved_db_path,
        conn=conn,
        job_manager=job_manager,
        events=events,
        people_service=people_service,
        registry_path=registry_path,
        prediction_service=prediction_service,
    )


def last_folder_file(config_dir: Path) -> Path:
    """Return path to the persisted last-folder marker."""
    return config_dir / "last_folder.txt"


def load_last_folder(config_dir: Path) -> Path | None:
    """Load last folder if recorded."""
    lf = last_folder_file(config_dir)
    if not lf.exists():
        return None
    try:
        return Path(lf.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def save_last_folder(config_dir: Path, folder: Path) -> None:
    """Persist last folder selection for ingest defaults."""
    config_dir.mkdir(parents=True, exist_ok=True)
    last_folder_file(config_dir).write_text(str(folder), encoding="utf-8")


def last_db_file(config_dir: Path) -> Path:
    return config_dir / "last_db.txt"


def load_last_db_path(config_dir: Path) -> Path | None:
    """Load last DB path if recorded."""
    lf = last_db_file(config_dir)
    if not lf.exists():
        return None
    try:
        return Path(lf.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def save_last_db_path(config_dir: Path, db_path: Path) -> None:
    """Persist last DB path selection."""
    config_dir.mkdir(parents=True, exist_ok=True)
    last_db_file(config_dir).write_text(str(db_path), encoding="utf-8")
