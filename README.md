# face-and-names v2 (greenfield)

All legacy code has been removed. This repository is now a clean slate for the v2 implementation with no backward-compatibility constraints.

## What remains
- Requirements source of truth: `docs/requirements.md`
- Legacy artifacts kept for reference only: model weights in `face_recognition_models`, sample data such as `faces.db`, and historical notes in `commit-notes.md`.

## Next steps before coding
1) Confirm the target tech stack and project layout (app, services, tests, tooling).
2) Define the initial database/schema plan and migration/reset strategy for new DB roots.
3) Document the build/run workflow to be used for v2 (package manager, env setup, lint/test commands).
4) Establish traceability: map planned milestones to the numbered requirements in `docs/requirements.md`.
