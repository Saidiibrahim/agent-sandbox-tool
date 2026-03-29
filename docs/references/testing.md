# Testing Guide

The test strategy is layered:

- fast unit coverage without Modal by default
- opt-in live Modal integration coverage
- optional server route tests when the `[server]` deps are installed

## Test layout

```text
tests/
├── fakes.py
├── test_artifacts.py
├── test_async_session.py
├── test_cli.py
├── test_config.py
├── test_diagnostics.py
├── test_manager.py
├── test_python_runner.py
├── test_server.py
├── test_session.py
├── test_state.py
├── test_tool.py
└── integration/
    └── test_modal_backend.py
```

## What belongs where

- `fakes.py`
  Deterministic backend doubles for sync and async session tests, including manifest capture and artifact file reads/downloads.
- `test_config.py`
  Config validation, security defaults, and timeout/resource guardrails.
- `test_session.py` and `test_async_session.py`
  Lifecycle mapping, structured execution results, and sync/async parity.
- `test_artifacts.py`
  Run IDs, sequence numbers, artifact preview/download, and path-safety checks.
- `test_state.py`
  Stored session/run persistence and list/read behavior.
- `test_manager.py`
  Cross-process reattach semantics and metadata preservation.
- `test_cli.py`
  JSON output and stable exit-code behavior.
- `test_diagnostics.py`
  Modal environment reporting without assuming the local machine is unconfigured.
- `test_server.py`
  Optional FastAPI route behavior, state-dir wiring, and exception-to-HTTP mapping. These tests skip if `fastapi`, `httpx`, or `pydantic-settings` are unavailable.
- `integration/test_modal_backend.py`
  Real Modal create/attach/exec/filesystem behavior with `MODAL_RUN_INTEGRATION=1`.

## Common commands

```bash
# Fast unit suite from a source checkout
PYTHONPATH=src pytest -m "not integration"

# Focused slices
PYTHONPATH=src pytest -q tests/test_artifacts.py tests/test_state.py tests/test_manager.py
PYTHONPATH=src pytest -q tests/test_cli.py tests/test_diagnostics.py

# Full verification after installing the package
pytest -m "not integration"
./scripts/execplan/check.sh
ruff check .
ruff format --check .
mypy src
python -m build

# Optional server route tests
pytest -q tests/test_server.py

# Live Modal integration
MODAL_RUN_INTEGRATION=1 pytest -m integration
```

## Verification expectations

- Treat `PYTHONPATH=src pytest -m "not integration"` as the source-tree baseline.
- When changing packaging, also run the installed-wheel or editable-install path so console scripts and optional extras are exercised.
- Keep integration failures separate from unit regressions; lack of Modal credentials is a verification gap, not a code failure.
- If the live Modal integration path fails, record the concrete failure in the active exec plan so the docs and state files stay honest.
