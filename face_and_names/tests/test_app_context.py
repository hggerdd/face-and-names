from __future__ import annotations

from pathlib import Path

from face_and_names import app_context
from face_and_names.app_context import AppContext, initialize_app, resolve_db_path


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
    assert db_path.exists()
    # Ensure schema applied
    tables = {
        row[0]
        for row in context.conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
    }
    assert "image" in tables and "face" in tables
