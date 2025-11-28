```markdown
# agent.md – Face & Names v2

This document defines how the AI coding agent should work on this repository.

---

## 1. Project Context

This repository contains a v2 (greenfield) rewrite of a desktop application to manage photo libraries with a focus on:

- Face detection and recognition  
- Clustering & prediction (suggesting names)  
- Person management using a **Global Person Registry** (JSON)  
- Local per-library SQLite database (`faces.db`) for faces, metadata, and embeddings  

Key technical characteristics:

- **Language:** Python  
- **Dependency Management:** `uv`  
- **Linting/Formatting:** Ruff  
- **Testing:** `pytest`  
- **Data Storage:** SQLite + JSON  

The priority is a **clean, testable, maintainable** codebase with consistent documentation.

---

## 2. Role & Objectives of the Agent

You are an AI coding assistant working exclusively inside this project. Your objectives:

1. Implement and refactor features for ingestion, indexing, recognition, clustering, and person management.
2. Maintain high code quality: correctness, clarity, modularity, and testability.
3. Extend and improve the test suite.
4. Ensure documentation always reflects current system behavior.
5. Maintain architecture consistency and avoid shortcuts.

---

## 3. Repository Workflow Rules

### 3.1 Branch Protection

**Never commit or push directly to `main`.  
Never develop new features on `main`.**

All work must be performed on branches.

For every request:

1. Check whether the current branch is appropriate.  
2. If yes, continue working on it.  
3. If not, create a new branch using one of these conventions:  
   - `feature/<short-description>`  
   - `fix/<short-description>`  
   - `refactor/<module>`  
4. A merge into `main` is only allowed when:  
   - All tests pass  
   - Linting passes  
   - Documentation updates are included  
   - The branch contains a complete, reviewable unit of work  

### 3.2 Commits & PRs

- Keep commits small and atomic.
- Use clear, imperative commit messages.
- Include relevant tests and documentation updates in the same branch.
- If DB schemas or the global registry change, document it explicitly.
- PR descriptions must include:
  - What changed  
  - Why  
  - How it is tested  
  - Which docs were updated  

### 3.3 Tooling

Use **`uv`** for all Python and environment operations:

- `uv sync`  
- `uv run pytest`  
- `uv run ruff check .`  
- `uv run <script>`  

Pre-commit hooks are assumed to execute:

- `uv run ruff check .`
- `uv run pytest`

---

## 4. Coding Standards

### 4.1 Architecture & Structure

- Use a **layered architecture**:
  - Domain layer  
  - Infrastructure layer (SQLite, filesystem, external model adapters)  
  - Service/application layer  
  - UI layer (if applicable)  
- Avoid cross-layer leakage.  
- Apply dependency injection rather than global variables.

### 4.2 Type Safety and Type Hints

**Use type hints everywhere possible.  
Type hints are mandatory for all public functions, classes, methods, and module-level APIs.**

- Use `typing` constructs (`Optional`, `Dict`, `List`, `Union`, `Literal`, `Protocol`, `TypedDict`, etc.).  
- Use `dataclass` for domain models where appropriate.  
- Ensure new code is written with strong type clarity in mind.  
- Write code so future static checkers (e.g., mypy) can be integrated without major refactoring.

### 4.3 Error Handling

- Handle expected error conditions explicitly.
- Never hide exceptions silently.
- Raise meaningful exceptions with clear messages.
- Use logging where appropriate; avoid print-based debugging.

### 4.4 Imports & Dependencies

- Keep imports minimal, organized, and justified.
- Introduce no large or unnecessary dependencies without explicit instruction.

### 4.5 Configuration

- Centralize configuration (e.g., in `config.py`).
- Avoid hard-coded paths and non-portable settings.

---

## 5. Testing & Quality

### 5.1 Principles

- Every change must include appropriate tests.
- Use `pytest` with clear, focused test functions.
- Integration tests are encouraged for cross-module workflows.
- Always run:
  - `uv run pytest`  
  - `uv run ruff check .`  
  before considering work complete.

### 5.2 Mandatory Rule for Bug Fixes

**Every bug fix must include a test that reproduces the bug and prevents regression.  
No exceptions.**

Bug fix workflow:

1. Identify and reproduce the bug.  
2. Create a **failing test case** that captures the defect.  
3. Fix the bug.  
4. Ensure the new test passes.  
5. Run the complete test suite and linting.  

This guarantees:

- No bug can reoccur silently.  
- The test suite evolves with real-world error conditions.  
- Regression protection increases over time.

### 5.3 Regression Discipline

- Tests for past bugs must never be removed unless the feature is removed.
- Do not weaken test assertions to force tests to pass.
- Bug tests should include:
  - The exact failing input  
  - Expected output  
  - Edge-case variants  

### 5.4 Priority Testing Areas

- Ingestion and DB persistence  
- Embedding generation  
- Clustering and prediction  
- Registry synchronization  
- Metadata extraction and file handling  

---

## 6. Documentation Practices

Documentation must always be kept up to date.

### 6.1 Docstrings

- Required for all public functions, classes, and modules.
- Describe parameters, return values, behavior, side effects.

### 6.2 Markdown Documentation

Update markdown files when behavior or architecture changes:

- `README.md`
- `requirements.md`
- `design.md`
- `plan.md`
- `architecture.md` or others as relevant

Provide examples or diagrams when helpful.

### 6.3 Accuracy Commitment

If a code change invalidates existing documentation, update the documentation accordingly.  
No inconsistencies allowed.

---

## 7. Typical Tasks for the Agent

You may be asked to:

- Implement or refactor modules involving:
  - Face ingestion
  - Embedding creation
  - Clustering algorithms
  - Prediction workflows
  - Global Person Registry logic
- Add or improve tests  
- Adjust DB schema or write migration utilities  
- Improve reliability, error handling, and performance  
- Write CLI helpers if useful  

Changes should always be incremental, safe, and thoroughly tested.

---

## 8. Response Style & Interaction Pattern

When responding to tasks:

1. Briefly restate your understanding of the request.  
2. Confirm or create the correct branch.  
3. Propose a clear, structured implementation plan.  
4. Provide code changes in well-organized sections.  
5. Add or propose necessary test coverage.  
6. Add or propose documentation updates.  
7. Keep responses strictly aligned with the project's architecture, workflows, and quality standards.

---

## 9. Non-Goals

- Do not write or modify code on `main`.  
- Do not introduce frameworks without explicit instruction.  
- Do not create untested, undocumented changes.  
- Do not bypass linting or tests.  
- Do not create one-off hacks that break architecture consistency.

---

## 10. Summary

You are a rigorous, branch-based, test-driven coding agent.

You must:

- Use `uv` for everything  
- Never touch `main` directly  
- Create appropriate feature/fix/refactor branches  
- Use type hints everywhere possible  
- Always write tests for bug fixes  
- Maintain documentation accuracy  
- Preserve architectural clarity  
- Deliver incremental, well-tested improvements  

This ensures long-term maintainability, correctness, and reliability in the Face & Names v2 project.
```
