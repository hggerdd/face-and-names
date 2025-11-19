# Face-and-Names v2 – Proposed Directory Structure (Pre-Code)

Planned layout for the new codebase. No files created yet.

```
face_and_names/
  __init__.py
  app.py                     # PyQt entry point
  ui/
    __init__.py
    main_window.py
    face_tile.py
    faces_workspace.py
    import_view.py
    clustering_view.py
    prediction_review_view.py
    people_view.py
    diagnostics_view.py
    export_import_view.py
    data_insights_view.py
    settings_view.py
    components/             # shared widgets (progress panels, histograms, overlay editor)
  services/
    __init__.py
    ingest_service.py
    detector_adapter.py
    prediction_service.py
    clustering_service.py
    faces_workspace_controller.py
    people_service.py
    export_import_service.py
    diagnostics_service.py
    workers.py
  models/                    # DB access layer, DTOs
    __init__.py
    db.py
    repositories.py
    schema.sql               # optional embedded DDL
  config/
    __init__.py
    loader.py
    defaults.py
  logging/
    __init__.py
    setup.py
  utils/
    __init__.py
    hashing.py
    imaging.py               # EXIF, orientation, thumbnails
    identity.py              # relink helpers
    paths.py                 # DB Root utilities
  tests/
    conftest.py
    ... per feature ...
```

Top-level files to add later:
- `pyproject.toml`, `uv.lock`
- `README.md` (already present), `LICENSE`
- `docs/` (already populated)
- Tooling configs (e.g., `.ruff.toml`, `mypy.ini`) if adopted
