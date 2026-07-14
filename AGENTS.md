# AGENTS.md

Applies to the entire repository unless overridden by a closer nested `AGENTS.md`.

## Project

Face & Names v2 is a Python desktop application for:

* photo ingestion and indexing
* face detection and embedding generation
* clustering and identity prediction
* person management
* global JSON person registry
* per-library SQLite database

Tooling:

* Python version from `pyproject.toml`
* `uv`
* Ruff
* pytest
* SQLite
* JSON

Primary priorities:

1. user data integrity
2. correctness
3. testability
4. maintainability
5. minimal scope

---

## Agent Workflow

Before editing:

1. Inspect relevant code, tests, configuration, and documentation.
2. Run `git status`.
3. Identify unrelated existing changes.
4. Determine the smallest required change set.

During work:

* Modify only task-relevant files.
* Preserve unrelated user changes.
* Avoid unrelated cleanup and repository-wide formatting.
* Prefer direct implementation for small tasks.
* For risky or architectural tasks, state a short plan first.
* Make conservative assumptions when they do not risk data or compatibility.
* Ask only when ambiguity materially affects correctness, architecture, or data integrity.

At completion report:

* changed files
* relevant design decisions
* commands executed
* command results
* remaining risks or assumptions

Never claim a check passed unless it was executed successfully.

---

## Git Safety

Without explicit user instruction, never:

* create or switch branches
* commit
* push
* merge
* rebase
* reset
* discard changes
* force-push
* run `git reset --hard`
* run `git clean -fd`

Never overwrite or revert unrelated user changes.

Before a requested commit:

* inspect the diff
* exclude unrelated files
* summarize commit scope
* use an imperative commit message

---

## Environment and Dependencies

Use `uv` exclusively.

Allowed patterns:

```bash
uv sync
uv add <package>
uv add --dev <package>
uv remove <package>
uv run <command>
```

Never use or recommend `pip`.

Rules:

* Do not edit `uv.lock` manually.
* Do not add, remove, or upgrade dependencies unless required.
* Ask before adding a runtime dependency unless explicitly requested.
* Prefer the standard library when appropriate.
* Keep `pyproject.toml` and `uv.lock` consistent.
* Do not download models, datasets, binaries, or external assets without explicit permission.

---

## Architecture

Architecture must optimize for:

1. correctness
2. testability
3. explicit dependencies
4. data safety
5. low coupling

Use clear boundaries between:

* domain
* application/services
* infrastructure
* UI

Dependency direction:

```text
UI -> Application -> Domain
Infrastructure -> Domain/Application interfaces
Domain -> nothing external
```

Rules:

* Domain code must not import SQLite, filesystem, UI, ML frameworks, or external services.
* UI must not access SQLite, registry files, or ML models directly.
* SQL belongs in infrastructure.
* Model-specific tensors and framework types belong inside adapters.
* Application services orchestrate use cases and transaction boundaries.
* Use dependency injection at boundaries.
* Avoid mutable global state.
* Avoid service locators and hidden dependencies.
* Do not add abstractions without a concrete boundary or testability benefit.

---

## Testability-First Design

All new and modified architecture must be optimized for automated testing.

Rules:

* Separate pure logic from I/O.
* Separate computation from orchestration.
* Separate side effects from decision logic.
* Encapsulate filesystem, database, time, randomness, configuration, and ML models behind explicit boundaries.
* Pass dependencies explicitly.
* Avoid direct dependency construction inside business logic.
* Prefer small, focused functions with explicit inputs and outputs.
* Avoid functions that combine validation, persistence, model execution, logging, and UI updates.
* Prefer deterministic logic.
* Inject clocks and random generators when behavior depends on them.
* Make transaction boundaries explicit.
* Return structured results instead of requiring tests to inspect logs or global state.
* Keep error paths testable.
* Design bulk operations so individual steps can be tested independently.
* Avoid private logic that can only be tested through the full UI.
* Extract non-trivial UI logic into testable application or domain functions.
* Do not use singletons for databases, registries, model instances, configuration, or application state.
* Reuse expensive model instances through explicit lifecycle management, not global construction.
* Introduce interfaces or protocols when they isolate external behavior or provide a meaningful test seam.
* Do not create interfaces solely to satisfy an architectural pattern.

A component is insufficiently designed when meaningful behavior can only be tested using:

* a real photo library
* a real database
* a real registry
* a downloaded ML model
* network access
* the full desktop UI

Refactor such behavior behind testable boundaries before extending it.

---

## Data Safety

Treat photos, names, metadata, databases, registries, and embeddings as sensitive user data.

Never:

* modify, rename, move, or delete original photos unless explicitly requested
* run tests against real user data
* silently recreate or reset a database
* silently replace a malformed registry with an empty registry
* silently regenerate all embeddings
* upload project or user data to external services
* log full names, embeddings, registry contents, or sensitive metadata

For writes:

* validate before mutation
* use transactions where supported
* use atomic file replacement where practical
* prevent partial state
* preserve recovery paths for destructive migrations
* make bulk operations explicit and preferably dry-runnable

Tests must use temporary directories, disposable databases, temporary registries, synthetic embeddings, and non-personal test images.

---

## SQLite

Rules:

* Use parameterized SQL.
* Keep SQL inside infrastructure.
* Use transactions for multi-step writes.
* Do not expose raw connections or cursors outside infrastructure.
* Avoid hidden writes in read methods.
* Enable and test required foreign-key behavior.
* Convert rows into typed models.
* Do not interpolate values into SQL strings.

Schema changes require:

* explicit schema version
* migration path
* migration tests
* clean-database tests
* defined unsupported-version behavior
* no silent data deletion
* no automatic database recreation after migration failure

---

## Global Person Registry

Rules:

* Use stable immutable person IDs.
* Never use names as identifiers.
* Preserve unknown fields where practical.
* Validate the full registry before replacement.
* Write to a temporary file and replace atomically.
* Never overwrite confirmed user decisions with predictions.
* Do not silently merge conflicting identities.
* Preserve provenance for imported, predicted, confirmed, and rejected assignments.
* Keep synchronization deterministic and testable.

---

## Face Recognition and Embeddings

Persist compatibility metadata where applicable:

* model ID and version
* preprocessing version
* embedding dimension
* normalization
* similarity metric
* detection or crop strategy

Rules:

* Never compare incompatible embeddings.
* Validate dimensions before storage and comparison.
* Separate detection, alignment, embedding, matching, clustering, and naming.
* Keep thresholds configurable.
* Do not hard-code thresholds in unrelated logic.
* Predictions are suggestions, not confirmed identities.
* Never overwrite manual confirmation with a prediction.
* Preserve prediction source, model version, confidence, and status.
* Never auto-merge persons based only on a similarity threshold.
* Prefer false negatives over destructive false-positive identity merges.
* Bulk re-embedding or re-indexing requires explicit user intent.
* Do not mix partially migrated embedding versions.

---

## Filesystem

Rules:

* Use `pathlib.Path`.
* Avoid hard-coded absolute paths.
* Do not assume OS-specific path behavior.
* Restrict traversal to configured roots.
* Handle symlinks deliberately.
* Do not use filenames as stable IDs.
* Avoid overwriting files unless explicitly intended.
* Use atomic writes where practical.
* Handle missing, corrupt, inaccessible, duplicate, and unsupported files explicitly.
* Clean temporary files after failure.

---

## Configuration

Rules:

* Centralize configuration.
* Use typed configuration where practical.
* Validate configuration at startup.
* Keep defaults separate from user-specific values.
* Load environment variables at application boundaries.
* Do not scatter environment reads across modules.
* Do not commit secrets, tokens, credentials, or local paths.
* Keep model names, thresholds, paths, and database settings configurable.

---

## Python and Types

Use modern Python syntax:

```python
str | None
list[str]
dict[str, int]
```

Type hints are required for:

* public APIs
* application service boundaries
* repository interfaces
* model adapter interfaces
* persistence conversion functions

Prefer:

* dataclasses for structured domain/application data
* `Protocol` for meaningful boundaries
* enums or `Literal` for constrained states
* explicit result objects over loosely typed dictionaries

Avoid:

* unnecessary `Any`
* boolean mode flags when an enum is clearer
* casts that hide type defects
* framework types leaking across boundaries

Follow configured type-checking tools. Do not add a new type checker unless requested.

---

## Coding Rules

* Prefer clear code over clever code.
* Keep functions focused.
* Make side effects explicit.
* Validate early.
* Avoid deep nesting.
* Avoid duplicated business rules.
* Preserve public behavior unless explicitly changed.
* Avoid broad exception handling.
* Never silently swallow exceptions.
* Wrap exceptions with useful context and preserve causes.
* Use logging, not `print`, for runtime diagnostics.
* Do not perform expensive initialization at import time.
* Do not hide dependencies inside modules or constructors.
* Avoid circular imports and wildcard imports.

---

## Testing

Use pytest.

Add or update tests for every behavioral change.

Bug fixes:

1. reproduce the bug
2. add a failing regression test
3. implement the fix
4. run the focused test
5. run the relevant suite

Exceptions:

* Documentation-only changes need no new tests.
* Pure refactors need no new tests if behavior is already adequately covered.
* When deterministic regression testing is impractical, explain why and add the strongest reliable protection available.

Tests must be:

* isolated
* deterministic
* local
* independent of network access
* independent of real user files
* independent of downloaded ML models where possible

Do not:

* weaken assertions to make tests pass
* remove regression tests without removing the behavior
* mock the unit under test
* over-mock pure internal logic
* test implementation details when behavior can be tested
* depend on test execution order

Prioritize tests for:

* ingestion
* duplicate handling
* SQLite persistence and migrations
* registry validation and atomic writes
* stable IDs
* embedding compatibility
* clustering and prediction provenance
* protection of confirmed identities
* corrupt and inaccessible files
* interrupted bulk operations

---

## Verification

During development, run focused checks first.

Examples:

```bash
uv run pytest tests/path/test_module.py
uv run pytest tests/path/test_module.py::test_case
uv run ruff check path/to/file.py
```

Before declaring implementation complete, normally run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Also run configured type checks or repository-specific checks when present.

Report each command as:

* passed
* failed due to current change
* failed due to pre-existing issue
* not executed

Do not modify tests, Ruff configuration, or CI merely to suppress valid failures.

---

## Documentation

Update documentation only when changes affect:

* installation or execution
* user-visible behavior
* configuration
* architecture
* public APIs
* database schema or migrations
* registry format
* embedding compatibility
* CLI behavior
* recovery procedures

Do not:

* edit unrelated documentation
* document unimplemented behavior
* add redundant docstrings

Docstrings should explain non-obvious behavior, constraints, side effects, errors, units, formats, or compatibility requirements.

---

## Performance and Concurrency

Rules:

* Process large libraries incrementally or in batches.
* Avoid loading entire libraries into memory.
* Avoid repeated image decoding and model loading.
* Batch database writes where safe.
* Do not trade data integrity for speed.
* Support cancellation, progress reporting, and resumability where practical.

When using concurrency:

* define ownership of SQLite connections
* prevent concurrent registry writes
* define cancellation and partial-failure behavior
* avoid duplicate concurrent processing
* keep progress updates thread-safe
* do not block the UI thread

---

## Security and Privacy

Treat all file content and metadata as untrusted input.

Never:

* use `eval` or `exec`
* deserialize unsafe formats from untrusted files
* construct shell commands from unsanitized strings
* expose sensitive data in errors or logs
* add telemetry
* send user data externally

Prefer Python APIs over shell commands.

When shell execution is necessary, use argument lists rather than interpolated command strings.

---

## UI

* Keep business logic outside event handlers.
* Keep long-running tasks off the UI thread.
* Move testable decisions into domain or application functions.
* Make destructive actions explicit.
* Require confirmation for destructive bulk operations.
* Do not silently re-index or re-embed on startup.
* Keep UI state separate from persisted domain state.
* Present actionable errors without hiding technical causes from logs.

---

## Completion Criteria

A task is complete when relevant criteria are satisfied:

* requested behavior implemented
* unrelated behavior preserved
* architecture remains testable
* relevant tests added or updated
* relevant checks executed
* migrations implemented and tested when needed
* documentation updated when needed
* no unrelated files changed
* remaining risks disclosed

---

## Prohibited Shortcuts

Never:

* use `pip`
* hide failing tests
* weaken assertions without justification
* suppress valid lint findings
* silently swallow errors
* store predictions as confirmed identities
* mix incompatible embeddings
* reset user data
* test against real user data
* add hidden network access or telemetry
* introduce unnecessary frameworks
* perform unrelated refactors
* claim checks passed when not run
