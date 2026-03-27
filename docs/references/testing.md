# Testing Guide

The test suite is designed to run fast without external dependencies by default, with opt-in integration tests for end-to-end validation against real Modal infrastructure.

---

## Test Architecture

```
tests/
├── fakes.py                          # Test doubles (no Modal dependency)
├── test_config.py                    # Config validation & security defaults
├── test_python_runner.py             # Runner subprocess execution (local)
├── test_session.py                   # Session lifecycle with FakeBackend
├── test_tool.py                      # Tool payload serialization
├── test_async_session.py             # Async session with FakeAsyncBackend
└── integration/
    └── test_modal_backend.py         # E2E with real Modal (opt-in)
```

---

## Test Doubles (fakes.py)

The library uses fake backends instead of mocks for deterministic testing.

### FakeBackend / FakeAsyncBackend

Both implement the corresponding `SyncSandboxBackend` / `AsyncSandboxBackend` protocols:

- Track `started` state and `commands` list
- Accept a queue of pre-built `BackendCommandResult` objects
- Pop results from the queue on each `run()` / `arun()` call

### backend_result() factory

Creates a `BackendCommandResult` with sensible defaults (exit_code=0, timed_out=False, timestamps=now), so tests only specify the fields they care about.

---

## Running Tests

```bash
# All unit tests (no Modal credentials needed)
pytest

# With coverage
pytest --cov=agent_sandbox --cov-report=term-missing

# Specific test file
pytest tests/test_session.py

# Integration tests (requires Modal credentials)
MODAL_RUN_INTEGRATION=1 pytest tests/integration/

# Full CI equivalent
ruff check . && ruff format --check . && mypy src && pytest
```

---

## What Each Test File Covers

### test_config.py
- Security-by-default: `NetworkPolicy()` defaults to `BLOCKED`
- `ALLOWLIST` mode requires non-empty `cidr_allowlist`
- `BLOCKED` / `ALLOW_ALL` modes reject `cidr_allowlist`
- Field validation (empty app_name, relative working_dir, etc.)

### test_python_runner.py
- Runs `PYTHON_RUNNER_BOOTSTRAP` as a local subprocess
- Validates final expression extraction (`"2 + 2"` → `value_repr = "4"`)
- Validates exception capture without crashing the runner
- Validates stdout capture from `print()` calls

### test_session.py
- Lazy initialization (sandbox not created until first use)
- Python result mapping from `BackendCommandResult` → `ExecutionResult`
- Shell non-zero exit code handling
- Session state transitions (close, detach, attach)

### test_tool.py
- `PythonSandboxTool.__call__()` returns JSON-serializable dict
- Error handling: `AgentSandboxError` → structured error payload

### test_async_session.py
- Async session execution with `FakeAsyncBackend`
- Mirrors sync session test coverage

### integration/test_modal_backend.py
- **Opt-in**: Requires `MODAL_RUN_INTEGRATION=1` environment variable
- **Requires**: Valid Modal credentials configured
- Tests:
  - Python execution in a real sandbox
  - File persistence across multiple `run_python()` calls in the same sandbox
  - Shell command execution
  - Timeout handling with real `ExecTimeoutError`

---

## CI Pipeline (.github/workflows/ci.yml)

The CI runs on every push and PR:

1. **Matrix**: Python 3.11 and 3.12
2. **Steps**:
   - `ruff check .` — Linting
   - `ruff format --check .` — Format verification
   - `mypy src` — Strict type checking
   - `pytest` — Unit tests with coverage
3. **Integration tests**: Available via manual workflow dispatch with Modal credentials passed as secrets
