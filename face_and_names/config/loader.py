"""
Configuration loader scaffold.
"""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

from face_and_names.config.defaults import DEFAULTS


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries without mutating the originals."""
    merged: dict[str, Any] = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path) -> dict[str, Any]:
    """
    Load a TOML config file and merge it over defaults.
    Missing files return defaults; malformed files raise ValueError.
    """
    if path.is_dir():
        raise IsADirectoryError(f"Config path points to a directory: {path}")

    user_config: dict[str, Any] = {}
    if path.exists():
        try:
            with path.open("rb") as fh:
                user_config = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:  # pragma: no cover - exercised via tests
            raise ValueError(f"Invalid config file {path}: {exc}") from exc

    return _deep_merge(DEFAULTS, user_config)
