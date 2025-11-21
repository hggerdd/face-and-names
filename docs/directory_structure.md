# Face-and-Names v2 — Directory & Documentation Structure

Current layout (reflecting early implementation):

```
face_and_names/
  app.py, app_context.py, __main__.py
  config/           # config loader/defaults
  logging/          # logging setup
  models/           # SQLite schema + repositories
  services/         # ingest/detector scaffolds and placeholders
  ui/               # PyQt main window + import/faces pages
  utils/            # helpers (hashing/imaging/paths) — to be expanded
  tests/            # feature-aligned tests
docs/
  requirements.md   # source of truth
  plan.md, architecture.md, schema.md
  service_contracts.md, detector_adapter.md, model_runner.md
  ui.md, ui_wireframes.md, ui_todo.md
  testing.md, logging.md, traceability.md
  build_run.md, config.md, dependencies.md, hash_scheme.md, workers.md, directory_structure.md (this file)
```

Documentation is organized into the following families:
- **Requirements**: `requirements.md` (SSoT)
- **Architecture & Design**: `architecture.md`, `plan.md`, `workers.md`, `hash_scheme.md`
- **Schema & Storage**: `schema.md`
- **Service Contracts**: `service_contracts.md`, `detector_adapter.md`, `model_runner.md`
- **UI/UX**: `ui.md`, `ui_wireframes.md`, `ui_todo.md`
- **Testing & Observability**: `testing.md`, `logging.md`, `traceability.md` (coverage matrix), performance/accessibility budgets
- **Operations**: `build_run.md`, `config.md`, `dependencies.md`

Keep this map in sync as features land so contributors know where to update source materials.
