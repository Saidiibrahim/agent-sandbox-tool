# Repository Guidelines

## Project Structure & Module Organization
`src/agent_sandbox/` contains the library. Treat `session.py` and `tool.py` as the public API layer, `backend/` as the Modal-specific implementation boundary, and `execution/` as the protocol/bootstrap layer for Python execution. Shared types live in `config.py`, `models.py`, and `exceptions.py`. `tests/` mirrors the package structure; `tests/fakes.py` provides deterministic fake backends, and `tests/integration/test_modal_backend.py` covers real Modal behavior. Use `docs/` for architecture, module, execution-flow, and testing notes.

## Build, Test, and Development Commands
`pip install -e .[dev]` installs the package in editable mode with Ruff, MyPy, Pytest, and pre-commit.
`ruff check .` runs lint rules.
`ruff format --check .` verifies formatting; use `ruff format .` before committing if needed.
`mypy src` enforces the repo’s strict typing rules.
`pytest -m "not integration"` runs the default fast suite with coverage enabled via `pyproject.toml`.
`MODAL_RUN_INTEGRATION=1 pytest -m integration` runs live Modal tests; this requires `modal setup` or valid `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET`.
`pre-commit run --all-files` matches the configured local hooks.

## Coding Style & Naming Conventions
Target Python 3.11+ with 4-space indentation, double quotes, and a 100-character line limit. Use `snake_case` for modules and functions, `PascalCase` for classes and enums, and `ALL_CAPS` for constants. Keep public APIs fully typed; `mypy` is configured with `disallow_untyped_defs = true`. Prefer Pydantic models for config and protocol boundaries. Keep Modal SDK details inside `backend/modal_backend.py` instead of leaking them into session or tool layers.

## Testing Guidelines
Add tests next to the affected behavior, following the existing `tests/test_*.py` pattern. Prefer `FakeBackend` / `FakeAsyncBackend` over mocks so lifecycle and result mapping stay deterministic. Mark live infrastructure coverage with `@pytest.mark.integration`. When changing execution, session, or security behavior, cover timeout handling, protocol parsing, detach/close flows, and network-policy defaults.

## Commit & Pull Request Guidelines
Current history uses short imperative subjects such as `Add project documentation`. Follow that pattern with concise present-tense commit lines. PRs should explain the behavioral change, list the commands you ran, state whether integration tests were run or skipped, and call out any security-sensitive changes to network access, secrets, or sandbox lifecycle.

## Security & Configuration Tips
The default network policy is blocked; treat any relaxation as a security-relevant change. Never commit Modal credentials or sandbox secrets. Keep agent state and secrets outside the sandbox unless the change explicitly requires a reviewed exception.
