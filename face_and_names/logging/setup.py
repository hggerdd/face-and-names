"""
Logging setup scaffold (see docs/logging.md).
"""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_dir: Path | None = None, level: str = "INFO") -> None:
    """Configure basic structured logging placeholder."""
    log_dir = log_dir or Path(".") / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )
