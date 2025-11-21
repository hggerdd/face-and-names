from __future__ import annotations

from pathlib import Path

from face_and_names import app_context
from face_and_names.app_context import (
    AppContext,
    initialize_app,
    load_last_folder,
    load_last_db_path,
    resolve_db_path,
    save_last_db_path,
    save_last_folder,
)


def test_resolve_db_path_handles_relative(tmp_path: Path) -> None:
    config = {"db": {"path": "faces.db"}}
    resolved = resolve_db_path(config, base_dir=tmp_path)
    assert resolved == tmp_path / "faces.db"


def test_initialize_app_honors_env_paths(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "cfg"
    db_path = tmp_path / "custom" / "faces.db"
    monkeypatch.setenv(app_context.ENV_CONFIG_DIR, str(config_dir))
    monkeypatch.setenv(app_context.ENV_DB_PATH, str(db_path))

    context: AppContext = initialize_app()

    assert context.db_path == db_path
    assert context.config_path.parent == config_dir
    assert db_path.exists()
    assert context.job_manager is not None
    # Ensure schema applied
    tables = {
        row[0]
        for row in context.conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
    }
    assert "image" in tables and "face" in tables


def test_last_folder_persistence(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "cfg"
    folder = tmp_path / "photos"
    folder.mkdir()

    save_last_folder(cfg_dir, folder)
    loaded = load_last_folder(cfg_dir)

    assert loaded == folder


def test_last_db_path_used_when_present(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "cfg"
    db_path = tmp_path / "custom" / "faces.db"
    config_path = config_dir / "config.toml"

    save_last_db_path(config_dir, db_path)
    context = initialize_app(config_path=config_path)

    assert context.db_path == db_path
    assert load_last_db_path(config_dir) == db_path
