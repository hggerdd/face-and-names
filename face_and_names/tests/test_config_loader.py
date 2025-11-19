from pathlib import Path

import pytest

from face_and_names.config.defaults import DEFAULTS
from face_and_names.config.loader import load_config


def test_load_config_returns_defaults_when_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    loaded = load_config(config_path)
    assert loaded == DEFAULTS
    assert loaded is not DEFAULTS  # caller can mutate safely


def test_load_config_merges_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [ui]
        theme = "dark"

        [workers]
        cpu_max = 4

        [detector.yolo]
        weights_path = "/tmp/alt.pt"
        """,
        encoding="utf-8",
    )

    loaded = load_config(config_path)

    assert loaded["ui"]["theme"] == "dark"
    assert loaded["ui"]["density"] == DEFAULTS["ui"]["density"]
    assert loaded["workers"]["cpu_max"] == 4
    assert loaded["workers"]["gpu_max"] == DEFAULTS["workers"]["gpu_max"]
    assert loaded["detector"]["yolo"]["weights_path"] == "/tmp/alt.pt"
    assert loaded["detector"]["default"] == DEFAULTS["detector"]["default"]


def test_load_config_raises_value_error_on_bad_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("this is not valid toml", encoding="utf-8")

    with pytest.raises(ValueError):
        load_config(config_path)
