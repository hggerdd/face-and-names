"""
Logging setup scaffold (see docs/logging.md).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(
    log_dir: Path | None = None,
    level: str = "INFO",
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    """Configure structured logging with console + rotating file handlers."""
    log_dir = log_dir or Path(".") / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"
    # Clear previous log at startup
    if log_path.exists():
        try:
            log_path.unlink()
        except Exception:
            pass
    handlers = [
        RotatingFileHandler(log_path, maxBytes=max_bytes, backupCount=backup_count),
        logging.StreamHandler(),
    ]
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )
