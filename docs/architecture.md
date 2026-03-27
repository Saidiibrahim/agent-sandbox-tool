# Architecture Overview

`agent-sandbox-tool` is a Python library that implements **Pattern 2: Sandbox as Tool** for AI agent systems. It provides an embeddable API to execute untrusted Python code and shell commands in remote [Modal](https://modal.com) sandboxes while keeping agent state and secrets outside the sandbox.

**Version**: 0.1.0 (Alpha)
**Python**: 3.11+
**Dependencies**: `modal>=1.3.4,<2.0.0`, `pydantic>=2.8,<3.0`

---

## Layered Architecture

The codebase is organized into three distinct layers. Each layer has a single responsibility and communicates with the layer below it through well-defined interfaces.

```
┌──────────────────────────────────────────────────────────────────┐
│                       PUBLIC API LAYER                           │
│                                                                  │
│  ┌────────────────────────┐   ┌────────────────────────────┐    │
│  │    SandboxSession      │   │   AsyncSandboxSession      │    │
│  │    (sync, threading)   │   │   (async, asyncio)         │    │
│  │                        │   │                            │    │
│  │  start()               │   │  start()                   │    │
│  │  run_python(code)      │   │  run_python(code)          │    │
│  │  run_shell(command)    │   │  run_shell(command)        │    │
│  │  detach() / close()    │   │  detach() / close()        │    │
│  └───────────┬────────────┘   └──────────────┬─────────────┘    │
│              │                                │                  │
│  ┌───────────▼────────────────────────────────▼─────────────┐   │
│  │  Tool Wrappers (callable, agent-friendly)                │   │
│  │                                                          │   │
│  │  PythonSandboxTool    AsyncPythonSandboxTool             │   │
│  │  ShellSandboxTool     AsyncShellSandboxTool              │   │
│  │                                                          │   │
│  │  __call__(code) -> dict   (JSON-serializable payload)    │   │
│  │  execute(code)  -> ExecutionResult  (structured result)  │   │
│  └──────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│                      EXECUTION LAYER                             │
│                                                                  │
│  ┌──────────────────────────────┐  ┌─────────────────────────┐  │
│  │  python_runner.py            │  │  protocol.py            │  │
│  │                              │  │                         │  │
│  │  PYTHON_RUNNER_BOOTSTRAP     │  │  PythonExecutionRequest │  │
│  │  (injected into sandbox)     │  │  PythonExecutionResponse│  │
│  │                              │  │                         │  │
│  │  build_python_command()      │  │  PROTOCOL_VERSION = 1   │  │
│  │  build_python_request()      │  │                         │  │
│  │  parse_python_response()     │  │                         │  │
│  └──────────────────────────────┘  └─────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│                       BACKEND LAYER                              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Protocols (structural typing)                           │   │
│  │                                                          │   │
│  │  SyncSandboxBackend           AsyncSandboxBackend        │   │
│  │    .sandbox_id                  .sandbox_id              │   │
│  │    .is_started                  .is_started              │   │
│  │    .start() -> str              .astart() -> str         │   │
│  │    .run(cmd, stdin, timeout)    .arun(cmd, stdin, timeout│   │
│  │    .terminate()                 .aterminate()            │   │
│  │    .detach()                    .adetach()               │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│                         │                                        │
│  ┌──────────────────────▼───────────────────────────────────┐   │
│  │  ModalBackend (concrete implementation)                  │   │
│  │                                                          │   │
│  │  Implements both Sync and Async protocols                │   │
│  │  Wraps: modal.App, modal.Sandbox, modal.Image            │   │
│  │  Handles: creation, reattach, exec, timeout, cleanup     │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  Modal SDK   │
                   │  (external)  │
                   └──────────────┘
```

---

## Directory Structure

```
agent-sandbox-tool/
├── pyproject.toml                          # Build config, deps, tool settings
├── README.md                               # Project overview and usage examples
├── .pre-commit-config.yaml                 # Ruff linting/formatting hooks
├── .github/workflows/ci.yml               # CI: tests, lint, mypy, coverage
│
├── src/agent_sandbox/
│   ├── __init__.py                         # Public API: all user-facing exports
│   ├── config.py                           # ModalSandboxConfig, NetworkPolicy
│   ├── exceptions.py                       # Exception hierarchy
│   ├── logging.py                          # Package logger setup
│   ├── models.py                           # ExecutionResult, SandboxHandle, enums
│   ├── session.py                          # SandboxSession, AsyncSandboxSession
│   ├── tool.py                             # Agent tool wrappers (4 classes)
│   │
│   ├── backend/
│   │   ├── __init__.py
│   │   ├── base.py                         # Protocol definitions + BackendCommandResult
│   │   └── modal_backend.py                # Modal-specific implementation (~310 lines)
│   │
│   └── execution/
│       ├── __init__.py
│       ├── protocol.py                     # IPC request/response Pydantic models
│       └── python_runner.py                # Bootstrap script + builder/parser functions
│
└── tests/
    ├── __init__.py
    ├── fakes.py                            # FakeBackend, FakeAsyncBackend test doubles
    ├── test_config.py                      # Config validation tests
    ├── test_python_runner.py               # Runner subprocess tests
    ├── test_session.py                     # Session lifecycle tests
    ├── test_tool.py                        # Tool payload tests
    ├── test_async_session.py               # Async session tests
    └── integration/
        └── test_modal_backend.py           # E2E tests (opt-in, needs Modal creds)
```

---

## Module Dependency Graph

Arrows point from **importer** to **imported**. The graph is intentionally acyclic.

```
                         tool.py
                        /   |   \
                       /    |    \
                      v     v     v
              session.py  models.py  exceptions.py
              /   |    \
             /    |     \
            v     v      v
      config.py  models.py  execution/python_runner.py
                                    |
                                    v
                            execution/protocol.py


      backend/modal_backend.py
           /        |
          v         v
    config.py   backend/base.py
        |
        v
   exceptions.py
```

**Key observations:**
- `tool.py` depends on `session.py` but not on `backend/` directly
- `session.py` uses `TYPE_CHECKING` imports for backend types (no runtime coupling)
- `modal_backend.py` lazy-imports `modal` at call time via `_import_modal()`
- `protocol.py` and `exceptions.py` have zero internal dependencies
