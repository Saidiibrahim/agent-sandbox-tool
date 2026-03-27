# Module Reference

Detailed documentation for each module in the `agent_sandbox` package.

---

## config.py — Configuration & Security Policy

Defines all sandbox configuration using Pydantic models with strict validation.

### ModalSandboxConfig

The main configuration object. All fields have sensible defaults, so a minimal config only needs `app_name`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `app_name` | `str` | `"agent-sandbox"` | Modal app identifier |
| `python_version` | `str` | `"3.11"` | Python version for the sandbox image |
| `python_packages` | `tuple[str, ...]` | `()` | Pip packages to install in the image |
| `timeout_seconds` | `int` | `1800` (30 min) | Max sandbox lifetime (1s – 24h) |
| `idle_timeout_seconds` | `int \| None` | `300` (5 min) | Auto-shutdown after inactivity |
| `default_exec_timeout_seconds` | `int` | `120` (2 min) | Per-command timeout |
| `working_dir` | `str` | `"/workspace"` | Absolute path used as cwd inside sandbox |
| `shell_executable` | `str` | `"/bin/bash"` | Shell used for `run_shell()` commands |
| `max_output_chars` | `int` | `50000` | Max stdout/stderr chars before truncation |
| `max_value_repr_chars` | `int` | `10000` | Max chars for Python expression repr |
| `network` | `NetworkPolicy` | `BLOCKED` | Outbound network access policy |
| `verbose` | `bool` | `False` | Enable verbose Modal logging |
| `image` | `Any \| None` | `None` | Custom Modal image (overrides auto-build) |
| `secrets` | `tuple[Any, ...]` | `()` | Modal Secret objects to mount |
| `tags` | `dict[str, str]` | `{}` | Tags applied to the sandbox for identification |

### NetworkPolicy & NetworkMode

Controls outbound network access. **Security by default: all network access is blocked.**

```
NetworkMode
├── BLOCKED     (default) — No outbound connections allowed
├── ALLOW_ALL              — Full internet access
└── ALLOWLIST              — Only specified CIDRs permitted
```

Validation rules:
- `ALLOWLIST` mode **requires** a non-empty `cidr_allowlist`
- `BLOCKED` / `ALLOW_ALL` modes **reject** any `cidr_allowlist` entries

---

## models.py — Data Types

### ExecutionKind (enum)

```
PYTHON  — Python code execution
SHELL   — Shell command execution
```

### ExecutionStatus (enum)

```
SUCCEEDED     — Code ran successfully (exit code 0, no exceptions)
FAILED        — User code raised an exception or non-zero exit
TIMED_OUT     — Execution exceeded the timeout limit
BACKEND_ERROR — Infrastructure or protocol failure
```

### SandboxHandle

Returned by `session.start()` and `session.detach()`. Contains the identifiers needed to reconnect.

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `str` | UUID hex for this session |
| `sandbox_id` | `str` | Modal sandbox object ID |
| `app_name` | `str` | Modal app name |
| `working_dir` | `str` | Working directory path |

### ExecutionResult

The structured result returned from every execution. This is the primary data type consumers interact with.

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `ExecutionKind` | Python or shell |
| `status` | `ExecutionStatus` | Outcome category |
| `success` | `bool` | Convenience: `status == SUCCEEDED` |
| `command` | `tuple[str, ...]` | The command that was executed |
| `stdout` | `str` | Captured standard output |
| `stderr` | `str` | Captured standard error |
| `stdout_truncated` | `bool` | Whether stdout was truncated |
| `stderr_truncated` | `bool` | Whether stderr was truncated |
| `exit_code` | `int \| None` | Process exit code (None on timeout) |
| `value_repr` | `str \| None` | repr() of last Python expression |
| `value_repr_truncated` | `bool` | Whether value_repr was truncated |
| `error_type` | `str \| None` | Exception class name |
| `error_message` | `str \| None` | Exception message |
| `traceback` | `str \| None` | Full traceback string |
| `session_id` | `str` | Originating session ID |
| `sandbox_id` | `str \| None` | Modal sandbox ID |
| `started_at` | `datetime` | UTC timestamp when execution began |
| `completed_at` | `datetime` | UTC timestamp when execution ended |
| `duration_seconds` | `float` | Wall-clock duration |

**Methods:**
- `as_tool_payload() -> dict` — Serializes to JSON-compatible dict for agent tool responses
- `backend_error(...)` — Class method factory for creating error results

---

## exceptions.py — Exception Hierarchy

All exceptions inherit from `AgentSandboxError` so consumers can catch the entire hierarchy with a single except clause.

```
AgentSandboxError
│
├── ConfigurationError
│   Raised for invalid library configuration
│   (e.g., bad NetworkPolicy combinations)
│
├── SessionError
│   ├── SessionClosedError
│   │   Raised when using a session after close()
│   │
│   └── SessionDetachedError
│       Raised when using a session after detach()
│       without re-attaching
│
├── BackendError
│   Raised when Modal operations fail
│   │
│   └── SandboxStartupError
│       Raised when sandbox creation or reattach fails
│
└── ExecutionError
    Raised when the library cannot produce a
    trustworthy execution result
    │
    ├── ExecutionTimeoutError
    │   Raised when a timeout is represented as exception
    │
    └── ProtocolError
        Raised when the bootstrap script returns
        malformed JSON or inconsistent state
```

---

## session.py — Core Public API

### SandboxSession (synchronous)

Thread-safe session using `threading.RLock`. All public methods acquire the lock.

```python
from agent_sandbox import ModalSandboxConfig, SandboxSession

config = ModalSandboxConfig(app_name="my-agent")

# Context manager (recommended)
with SandboxSession(config) as session:
    result = session.run_python("2 + 2")
    print(result.value_repr)  # "4"

# Manual lifecycle
session = SandboxSession(config)
session.start()
result = session.run_shell("echo hello")
session.close()
```

### AsyncSandboxSession (asynchronous)

Identical API surface using `asyncio.Lock`.

```python
from agent_sandbox import ModalSandboxConfig, AsyncSandboxSession

config = ModalSandboxConfig(app_name="my-agent")

async with AsyncSandboxSession(config) as session:
    result = await session.run_python("2 + 2")
```

### Detach / Attach (sandbox persistence)

```python
# Detach: release session, keep sandbox running
session = SandboxSession(config)
handle = session.start()
handle = session.detach()
# session is now unusable

# Attach: reconnect to the running sandbox
session2 = SandboxSession.attach(handle.sandbox_id, config)
result = session2.run_python("2 + 2")  # same sandbox, new session
session2.close()
```

---

## tool.py — Agent Tool Wrappers

Thin callable wrappers that make sessions compatible with agent tool registries.

| Class | Sync/Async | Wraps |
|-------|-----------|-------|
| `PythonSandboxTool` | Sync | `session.run_python()` |
| `ShellSandboxTool` | Sync | `session.run_shell()` |
| `AsyncPythonSandboxTool` | Async | `session.run_python()` |
| `AsyncShellSandboxTool` | Async | `session.run_shell()` |

Each tool has:
- `name` — Tool identifier (`"sandbox_python"` or `"sandbox_shell"`)
- `description` — Human-readable description for the agent
- `__call__(code_or_command) -> dict` — Returns JSON-serializable payload; catches `AgentSandboxError` and returns a structured error instead of raising
- `execute(code_or_command) -> ExecutionResult` — Returns typed result; exceptions propagate

```python
from agent_sandbox import PythonSandboxTool, SandboxSession, ModalSandboxConfig

session = SandboxSession(ModalSandboxConfig())
tool = PythonSandboxTool(session)

# As a callable (for agent frameworks)
payload = tool("print('hello')\n2 + 2")
# payload is a dict: {"kind": "python", "status": "succeeded", "value_repr": "4", ...}

# For structured access
result = tool.execute("2 + 2")
print(result.value_repr)  # "4"
```

---

## execution/protocol.py — IPC Protocol Models

Defines the v1 JSON protocol used for communication between the host and the bootstrap script running inside the sandbox.

### PythonExecutionRequest

Sent as JSON via stdin to the bootstrap script.

| Field | Type | Default |
|-------|------|---------|
| `protocol_version` | `Literal[1]` | `1` |
| `code` | `str` | (required) |
| `working_dir` | `str \| None` | `None` |
| `max_output_chars` | `int` | `50000` |
| `max_value_repr_chars` | `int` | `10000` |

### PythonExecutionResponse

Received as JSON from stdout of the bootstrap script.

| Field | Type | Default |
|-------|------|---------|
| `protocol_version` | `Literal[1]` | `1` |
| `success` | `bool` | (required) |
| `runner_error` | `bool` | `False` |
| `stdout` | `str` | `""` |
| `stderr` | `str` | `""` |
| `stdout_truncated` | `bool` | `False` |
| `stderr_truncated` | `bool` | `False` |
| `value_repr` | `str \| None` | `None` |
| `value_repr_truncated` | `bool` | `False` |
| `error_type` | `str \| None` | `None` |
| `error_message` | `str \| None` | `None` |
| `traceback` | `str \| None` | `None` |

---

## execution/python_runner.py — Bootstrap Script

Contains `PYTHON_RUNNER_BOOTSTRAP`, an embedded Python script (~170 lines) that is injected into the sandbox and executed via `python -u -c <script>`.

### What the bootstrap script does

1. Reads a JSON `PythonExecutionRequest` from stdin
2. Validates the protocol version
3. Changes to the specified working directory
4. Sets up `TruncatingBuffer` wrappers for stdout/stderr capture
5. Uses `ast.parse()` to split user code into statements + trailing expression
6. Executes statements with `exec()` in a fresh namespace
7. Evaluates the trailing expression with `eval()` (REPL-like behavior)
8. Writes a JSON `PythonExecutionResponse` to stdout

### Key internal components

- **TruncatingBuffer**: An `io.TextIOBase` subclass that caps captured output at `max_output_chars` and sets a `truncated` flag
- **split_last_expression()**: AST-based function that detects if the last statement is a bare expression and separates it for evaluation
- **safe_repr()**: Wraps `repr()` to handle objects whose repr raises
- **clamp()**: Truncates strings to a character limit

### Helper functions (host-side)

- `build_python_command() -> tuple` — Returns the command tuple: `("python", "-u", "-c", BOOTSTRAP)`
- `build_python_request(...) -> PythonExecutionRequest` — Constructs the protocol request
- `parse_python_response(stdout) -> PythonExecutionResponse` — Validates JSON from stdout, raises `ProtocolError` on malformed data

---

## backend/base.py — Backend Abstraction

Defines the contracts that any sandbox backend must implement using Python's `Protocol` (structural subtyping).

### BackendCommandResult (dataclass)

The raw result returned by backend command execution, before mapping to `ExecutionResult`.

| Field | Type | Description |
|-------|------|-------------|
| `command` | `tuple[str, ...]` | The executed command |
| `stdout` | `str` | Raw stdout |
| `stderr` | `str` | Raw stderr |
| `exit_code` | `int \| None` | None on timeout |
| `timed_out` | `bool` | Whether execution timed out |
| `started_at` | `datetime` | UTC start time |
| `completed_at` | `datetime` | UTC end time |
| `sandbox_id` | `str \| None` | Backend sandbox identifier |
| `error_type` | `str \| None` | Error class name (timeout errors) |
| `error_message` | `str \| None` | Error description |

### SyncSandboxBackend (Protocol)

```python
class SyncSandboxBackend(Protocol):
    sandbox_id: str | None          # Current sandbox ID
    is_started: bool                # Whether sandbox is running
    def start() -> str              # Create/reattach, return sandbox_id
    def run(cmd, stdin, timeout)    # Execute command, return result
    def terminate()                 # Kill sandbox
    def detach()                    # Release connection
```

### AsyncSandboxBackend (Protocol)

Same interface with `async` methods prefixed with `a` (`astart`, `arun`, `aterminate`, `adetach`).

---

## backend/modal_backend.py — Modal Implementation

The concrete backend implementation (~310 lines). Implements both `SyncSandboxBackend` and `AsyncSandboxBackend` protocols in a single class.

### Sandbox creation

```
ModalBackend.start()
       │
       ├── Has sandbox_id? ──yes──► modal.Sandbox.from_id(id)  (reattach)
       │
       └── No sandbox_id ──► modal.App.lookup(app_name, create_if_missing=True)
                              │
                              └──► modal.Sandbox.create(
                                     app=app,
                                     image=_build_image(),    # debian_slim + pip packages
                                     timeout=...,
                                     verbose=...,
                                     block_network=... | cidr_allowlist=...,
                                     idle_timeout=...,
                                     secrets=[...]
                                   )
                              │
                              └──► sandbox.hydrate()
                              └──► sandbox.set_tags(tags)
                              └──► _ensure_workspace()  # mkdir -p working_dir
```

### Image building

- If `config.image` is provided, it is used directly
- Otherwise: `modal.Image.debian_slim(python_version=...)` with optional `.pip_install()`

### Network policy translation

| NetworkMode | Modal kwargs |
|-------------|-------------|
| `BLOCKED` | `block_network=True` |
| `ALLOW_ALL` | (no network kwargs) |
| `ALLOWLIST` | `cidr_allowlist=[...]` |

### Command execution

The `_execute()` / `_aexecute()` methods handle:
- Starting the process via `sandbox.exec()`
- Writing stdin and signaling EOF
- Waiting for completion
- Reading stdout/stderr
- Catching `ExecTimeoutError` and safely reading partial output
- Wrapping `modal.Error` as `BackendError`

### Safe read

The `_safe_read()` / `_asafe_read()` static methods handle the case where reading a stream fails after a timeout — they return an empty string rather than propagating the error.
