# Design Decisions

Key design decisions and their rationale.

---

## Pattern 2: Sandbox as Tool

The library implements "Pattern 2" from the agent sandbox taxonomy: the agent stays in-process on the host, and only code execution is delegated to the sandbox.

```
┌──────────────────────────────────┐     ┌──────────────────────────┐
│          HOST PROCESS            │     │     MODAL SANDBOX        │
│                                  │     │                          │
│  ┌──────────┐  ┌──────────────┐ │     │  ┌────────────────────┐  │
│  │  Agent   │  │  Session /   │ │     │  │  Bootstrap Script  │  │
│  │  (LLM)   │──│  Tool API    │─┼─────┼──│  (user code runs   │  │
│  │          │  │              │ │ IPC  │  │   here)            │  │
│  └──────────┘  └──────────────┘ │     │  └────────────────────┘  │
│                                  │     │                          │
│  State, secrets, orchestration   │     │  Untrusted code only     │
│  remain here                     │     │  No secrets, no state    │
└──────────────────────────────────┘     └──────────────────────────┘
```

**Why**: This gives the agent full control over what code runs and when, while ensuring untrusted code never has access to secrets, API keys, or agent state. The alternative (Pattern 1: agent runs inside the sandbox) makes secret management much harder.

---

## Network Blocked by Default

`NetworkPolicy` defaults to `NetworkMode.BLOCKED`, which translates to `block_network=True` in Modal.

**Why**: Untrusted code should not be able to exfiltrate data, call external APIs, or download malicious payloads. If network access is needed, it must be explicitly opted into via `ALLOW_ALL` or `ALLOWLIST` with specific CIDRs.

---

## JSON-over-stdin/stdout IPC Protocol

Python execution uses a structured JSON protocol rather than parsing raw stdout.

```
Host                          Sandbox
  │                              │
  │  stdin: JSON request         │
  │─────────────────────────────►│
  │                              │
  │  stdout: JSON response       │
  │◄─────────────────────────────│
  │                              │
```

**Why**:
- Separates user code output from control data
- Enables structured error reporting (type, message, traceback)
- Supports output truncation metadata (`stdout_truncated`, etc.)
- Makes the protocol versionable (`protocol_version: 1`)
- Decouples from Modal's internal process communication

---

## AST-Based Expression Splitting

The bootstrap script uses `ast.parse()` to detect if the last statement in user code is a bare expression, then evaluates it separately.

```python
# Input: "x = 5\nx + 1"

# AST analysis:
#   Statement 0: Assign(x = 5)     → exec()
#   Statement 1: Expr(x + 1)       → eval() → value_repr = "6"
```

**Why**: This gives a REPL-like experience. Without it, `"2 + 2"` would produce no output because Python's `exec()` discards expression values. With it, agents can write natural exploratory code and see results.

---

## Protocol-Based Backend Abstraction

The backend layer uses Python's `typing.Protocol` (structural subtyping) rather than ABC inheritance.

```python
class SyncSandboxBackend(Protocol):
    def start(self) -> str: ...
    def run(self, command, *, stdin_text, timeout_seconds) -> BackendCommandResult: ...
    def terminate(self) -> None: ...
    def detach(self) -> None: ...
```

**Why**:
- Any class that implements the right methods is a valid backend — no base class needed
- Test fakes don't need to inherit from anything
- Future backends (Docker, Firecracker, etc.) can be added without modifying existing code
- Aligns with Python's duck-typing philosophy

---

## Dual Sync/Async APIs

The library provides both `SandboxSession` (sync) and `AsyncSandboxSession` (async) with identical behavior.

**Why**: Agent frameworks vary — some are synchronous (LangChain tools), others are async (custom orchestrators, web servers). Providing both avoids forcing users into `asyncio.run()` wrappers or sync-to-async bridges.

**Trade-off**: The session logic is duplicated between the two classes. This is intentional — a shared base class would add complexity and make the sync/async boundary less clear.

---

## Lazy Sandbox Initialization

The sandbox is not created until the first `start()`, `run_python()`, or `run_shell()` call.

**Why**: Creating a sandbox involves network calls to Modal and can take several seconds. Lazy initialization means:
- Constructing a `SandboxSession` is instant
- The sandbox is only created when actually needed
- Multiple `run_*` calls reuse the same sandbox (idempotent `start()`)

---

## Output Truncation

Both stdout/stderr and value_repr have configurable character limits (`max_output_chars`, `max_value_repr_chars`) with truncation flags.

**Why**: Untrusted code can produce unbounded output (e.g., `print("x" * 10**9)`). Without truncation, this would consume all available memory on the host. The truncation flags allow consumers to detect when output was cut off and inform the user/agent.

---

## Tool Wrappers Never Raise

The `__call__()` method on tool wrappers catches all `AgentSandboxError` exceptions and converts them to structured error payloads.

```python
def __call__(self, code: str) -> dict[str, object]:
    try:
        return self.execute(code).as_tool_payload()
    except AgentSandboxError as exc:
        return ExecutionResult.backend_error(...).as_tool_payload()
```

**Why**: Agent frameworks typically expect tools to return data, not raise exceptions. An unhandled exception could crash the agent loop. By always returning a structured result, the agent can inspect the error and decide how to proceed.

---

## Lazy Modal Import

The `modal` package is imported at call time via `_import_modal()`, not at module level.

**Why**:
- Allows importing `agent_sandbox` without `modal` installed (e.g., for type checking or test fakes)
- Provides a clear error message if `modal` is missing
- Avoids side effects from Modal's import-time initialization
