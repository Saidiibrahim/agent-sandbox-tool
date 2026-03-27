# agent-sandbox-modal

`agent-sandbox-modal` is a small embeddable Python library for Pattern 2 sandboxing.

Your agent stays in your application process. When it needs to execute code, it calls this package, which runs the code in a remote Modal sandbox and returns a structured result.

## Why this package exists

This package is intentionally narrow:

- it is not a full agent framework
- it keeps agent state and secrets outside the sandbox
- it gives you a small typed Python API you can embed into existing agent loops
- it is designed to be safe by default, easy to test, and legible to coding agents

## Installation

```bash
pip install agent-sandbox-modal
modal setup
```

## Minimal usage

```python
from agent_sandbox import ModalSandboxConfig, SandboxSession

config = ModalSandboxConfig(
    app_name="my-agent-sandbox",
    python_packages=("pandas==2.2.2",),
)

with SandboxSession(config) as session:
    python_result = session.run_python(
        """
import math
print('running in sandbox')
radius = 3
math.pi * radius ** 2
"""
    )

    print(python_result.model_dump(mode="json"))

    shell_result = session.run_shell("python --version")
    print(shell_result.stdout)
```

## Agent-friendly wrapper

```python
from agent_sandbox import ModalSandboxConfig, PythonSandboxTool, SandboxSession

session = SandboxSession(ModalSandboxConfig(app_name="agent-tool-demo"))
python_tool = PythonSandboxTool(session)

payload = python_tool("print('hello from agent')\n2 + 2")
print(payload)
```

## Lifecycle model

`SandboxSession` owns the local lifecycle:

- `start()` creates or attaches to a sandbox
- `run_python()` executes Python in a fresh process inside the existing sandbox
- `run_shell()` executes shell commands inside the same sandbox
- `detach()` releases the local connection but leaves the remote sandbox running
- `close()` terminates the sandbox and detaches

Use `SandboxSession.attach(...)` if you want to reconnect later with a saved `sandbox_id`.

## Security defaults

The default configuration blocks all outbound network access. That is intentional. If an LLM can generate arbitrary shell or Python commands, the most common practical risk is exfiltration or misuse of credentials, not only container escape.

## MVP scope

Included now:

- Python execution
- shell execution
- one sandbox per session
- sandbox reuse across calls
- sync and async APIs
- structured results
- testable backend abstraction

Deferred on purpose:

- file upload/download APIs
- persisted workspaces and Volumes
- dependency installation at runtime
- provider-agnostic backends
- notebook-style stateful Python driver
- snapshots and pooling

## Repository knowledge

- Architecture: [ARCHITECTURE.md](./ARCHITECTURE.md)
- Planning workflow: [docs/PLANS.md](./docs/PLANS.md)
- Design docs: [docs/design-docs/index.md](./docs/design-docs/index.md)
- Product intent: [docs/PRODUCT_SENSE.md](./docs/PRODUCT_SENSE.md)
- Testing reference: [docs/references/testing.md](./docs/references/testing.md)

## Development

```bash
pip install -e .[dev]
ruff check .
ruff format --check .
mypy src
pytest -m "not integration"
./scripts/execplan/check.sh
```

Integration tests are opt-in:

```bash
export MODAL_RUN_INTEGRATION=1
pytest -m integration
```
