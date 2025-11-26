# Ruff linting

Ruff is used for both linting and formatting. Key settings (line length, Python target, rule selection, and heavy-asset exclusions) live in `ruff.toml` at the repo root.

## Quick commands
- Check: `uv run ruff check .`
- Auto-fix: `uv run ruff check --fix .`
- Format: `uv run ruff format .`

If you do not have the env synced yet, you can also run `uvx ruff check .` to use an ephemeral tool-only environment.
