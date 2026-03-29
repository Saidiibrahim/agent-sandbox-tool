# agent-sandbox-modal

`agent-sandbox-modal` is a library-first developer tool for running untrusted Python and shell code in Modal Sandboxes.

It is intentionally narrow:

- not a full agent framework
- designed for custom host-controlled workflows
- safe by default, typed, testable, and scriptable
- usable from Python, a local CLI, and an optional HTTP surface

## Why this package exists

Applications building agents usually do not need another orchestration framework. They need a reliable remote execution boundary they can embed into their own systems.

This project focuses on that boundary:

- a small public Python API
- explicit Modal-specific behavior behind a thin backend layer
- a session model that works both in-process and across separate CLI calls
- a blocked-by-default network posture

## Installation

Core library:

```bash
pip install agent-sandbox-modal
```

Optional HTTP API:

```bash
pip install 'agent-sandbox-modal[server]'
```

Set up Modal on the machine where you will run the tool:

```bash
modal setup
agent-sandbox doctor
```

## Quick start: Python API

```python
from agent_sandbox import ModalSandboxConfig, SandboxSession

config = ModalSandboxConfig(
    app_name="my-agent-sandbox",
    python_packages=("pandas==2.2.2",),
)

with SandboxSession(config) as session:
    result = session.run_python(
        """
from pathlib import Path
print("running in sandbox")
Path("note.txt").write_text("hello from modal")
2 + 2
"""
    )

    print(result.status)
    print(result.run_id)
    print(result.value_repr)
    print([artifact.path for artifact in result.artifacts])
```

## Quick start: cross-process reuse with the CLI

```bash
agent-sandbox session start --app-name my-agent-sandbox --json
agent-sandbox run python <session-id> --code "print('hello'); 21 * 2" --json
agent-sandbox run shell <session-id> "python --version" --json
agent-sandbox run list --session-id <session-id>
agent-sandbox artifact list <run-id>
agent-sandbox artifact show <run-id> note.txt
agent-sandbox artifact download <run-id> note.txt ./note.txt
agent-sandbox session terminate <session-id>
```

## Public API

Core building blocks:

- `ModalSandboxConfig`
- `SandboxSession`
- `AsyncSandboxSession`
- `SandboxManager`
- `LocalStateStore`
- `PythonSandboxTool`
- `ShellSandboxTool`

### Execution model

Default behavior is one reusable sandbox session with a fresh process per execution.

That means:

- Python globals do not persist between `run_python()` calls
- the filesystem does persist while the sandbox is alive
- every execution gets a `run_id`, `sequence_number`, structured status, stdout/stderr, and best-effort artifact metadata

### Session lifecycle

Sessions model:

- `created`
- `active`
- `detached`
- `terminated`

`detach()` releases the local connection but keeps the remote sandbox alive. `SandboxSession.attach(...)` reconnects using a stored `sandbox_id`.

### Artifact model

An artifact is currently a regular file under `working_dir` that was added or modified during a run.

Implemented now:

- best-effort artifact diffing per run
- metadata stored on `ExecutionResult`
- text preview via `read_artifact_text()` or `agent-sandbox artifact show`
- download via `download_artifact()` or `agent-sandbox artifact download`

Not implemented yet:

- durable artifact persistence after sandbox termination
- deleted-file tracking
- binary previews
- volume-backed artifact retention

## CLI reference

Global flags:

```bash
agent-sandbox --json --state-dir /tmp/sandbox-state <command>
```

Commands:

```bash
agent-sandbox doctor

agent-sandbox session start [config flags]
agent-sandbox session attach <sandbox-id> [config flags]
agent-sandbox session show <session-id>
agent-sandbox session list
agent-sandbox session terminate <session-id>

agent-sandbox run python <session-id> --code 'print("hi")'
agent-sandbox run python <session-id> --file script.py
agent-sandbox run shell <session-id> 'pytest -q'
agent-sandbox run show <run-id>
agent-sandbox run list [--session-id <session-id>]

agent-sandbox artifact list <run-id>
agent-sandbox artifact show <run-id> <path>
agent-sandbox artifact download <run-id> <path> <destination>

agent-sandbox serve --host 127.0.0.1 --port 8000
```

Exit codes:

- `0` success
- `10` run failed, timed out, or returned a terminal execution error
- `11` session/run/artifact not found
- `12` config or validation error
- `13` Modal missing or misconfigured
- `14` backend failure
- `15` unexpected internal error

## Optional HTTP API

The optional FastAPI service is intentionally thin. It depends on `SandboxManager` and `LocalStateStore`; it does not bypass the library or call Modal directly.

Implemented routes:

- `GET /health`
- `POST /sessions`
- `POST /sessions/attach`
- `GET /sessions`
- `GET /sessions/{session_id}`
- `POST /sessions/{session_id}/runs/python`
- `POST /sessions/{session_id}/runs/shell`
- `POST /sessions/{session_id}/terminate`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/artifacts`
- `GET /runs/{run_id}/artifacts/preview`

## Security notes

- outbound network is blocked by default
- fresh process per run is safer than a persistent interpreter, but filesystem state still persists within a sandbox session
- artifact preview/download is best-effort and depends on the sandbox still being alive
- the optional HTTP API uses only a simple bearer-token hook and is intended for local or trusted internal use, not multi-tenant SaaS

## Repository knowledge

- Architecture: [ARCHITECTURE.md](./ARCHITECTURE.md)
- Planning workflow: [docs/PLANS.md](./docs/PLANS.md)
- Active/completed initiatives: [docs/exec-plans/index.md](./docs/exec-plans/index.md)
- Design docs: [docs/design-docs/index.md](./docs/design-docs/index.md)
- Testing reference: [docs/references/testing.md](./docs/references/testing.md)

## Development

```bash
pip install -e .[dev,server]
ruff check .
ruff format --check .
mypy src
pytest -m "not integration"
./scripts/execplan/check.sh
python -m build
```

Integration tests remain opt-in:

```bash
MODAL_RUN_INTEGRATION=1 pytest -m integration
```
