# Architecture Overview

`agent-sandbox-tool` is a Python library for Pattern 2 sandboxing: the agent stays in the host process, while untrusted Python or shell execution runs inside a remote Modal sandbox. The main architectural constraint is deliberate: agent state, credentials, and orchestration stay on the host; the sandbox is only an execution substrate.

Read this file with [docs/design-docs/index.md](./docs/design-docs/index.md), [docs/PRODUCT_SENSE.md](./docs/PRODUCT_SENSE.md), and [docs/SECURITY.md](./docs/SECURITY.md).

## Top-Level Shape

The codebase has three layers.

1. Public API: `src/agent_sandbox/session.py` and `src/agent_sandbox/tool.py`
2. Execution protocol: `src/agent_sandbox/execution/`
3. Modal backend boundary: `src/agent_sandbox/backend/`

The public layer should not leak Modal SDK details. The execution layer owns the JSON request/response protocol and bootstrap behavior for Python execution. The backend layer is the only place where Modal-specific sandbox lifecycle mechanics belong.

## Layered Architecture

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
│  │  Tool wrappers return JSON-serializable payloads         │   │
│  │  but preserve typed `ExecutionResult` access internally  │   │
│  └──────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│                      EXECUTION LAYER                             │
│                                                                  │
│  `python_runner.py` injects the bootstrap script used inside     │
│  the sandbox. `protocol.py` defines versioned Pydantic request   │
│  and response models.                                            │
├──────────────────────────────────────────────────────────────────┤
│                       BACKEND LAYER                              │
│                                                                  │
│  `backend/base.py` defines backend protocols.                    │
│  `backend/modal_backend.py` implements Modal sandbox lifecycle,  │
│  command dispatch, timeout handling, and detach/terminate flows. │
└──────────────────────────────────────────────────────────────────┘
```

## Package Orientation

- `src/agent_sandbox/config.py`: typed configuration and network policy defaults
- `src/agent_sandbox/models.py`: shared result and handle types
- `src/agent_sandbox/exceptions.py`: stable exception hierarchy
- `src/agent_sandbox/session.py`: canonical sync and async session APIs
- `src/agent_sandbox/tool.py`: agent-facing wrappers around session methods
- `src/agent_sandbox/execution/protocol.py`: JSON-over-stdin/stdout schema
- `src/agent_sandbox/execution/python_runner.py`: bootstrap script and response parsing
- `src/agent_sandbox/backend/modal_backend.py`: only Modal-specific implementation surface
- `tests/`: mirrors package responsibilities, with `tests/fakes.py` as the deterministic backend substitute

## Dependency Rules

- `tool.py` may depend on `session.py`, shared models, and exceptions. It should not call Modal directly.
- `session.py` may depend on shared models, config, and execution helpers. It should talk to a backend through the protocol defined in `backend/base.py`.
- `execution/` must stay backend-agnostic.
- `backend/modal_backend.py` may depend on Modal, but Modal concerns should stop there.
- Security-sensitive defaults, especially network policy, belong in `config.py` and the security docs, not as ad hoc call-site overrides.

## Repository Layout

```
agent-sandbox-tool/
├── AGENTS.md
├── ARCHITECTURE.md
├── README.md
├── docs/
│   ├── design-docs/
│   ├── exec-plans/
│   ├── generated/
│   ├── product-specs
│   ├── references/
│   ├── DESIGN.md
│   ├── FRONTEND.md
│   ├── PLANS.md
│   ├── PRODUCT_SENSE.md
│   ├── QUALITY_SCORE.md
│   ├── RELIABILITY.md
│   └── SECURITY.md
├── scripts/
│   ├── execplan/
│   └── generate_db_schema.py
├── src/agent_sandbox/
└── tests/
```

## Architectural Invariants

- The host process is authoritative for secrets, state, and orchestration.
- The default outbound network policy is blocked.
- The Python execution path must return structured data, not brittle text parsing.
- The library supports both sync and async consumers without changing semantics.
- Fake backends are preferred for deterministic tests; live Modal coverage remains opt-in.
