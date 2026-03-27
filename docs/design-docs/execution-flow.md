# Execution Flow

This document traces the complete lifecycle of code execution through the library, from user call to structured result.

---

## Python Execution Flow

The Python execution path is the most complex flow in the library. It uses a JSON-over-stdin/stdout IPC protocol to communicate with a bootstrap script injected into the sandbox.

```
   Agent / User Code
          │
          │  session.run_python("x = 5\nx + 1")
          ▼
┌─────────────────────────────────────────────────────────────┐
│  SandboxSession.run_python()                    session.py  │
│                                                             │
│  1. Acquire lock (threading.RLock / asyncio.Lock)           │
│  2. Lazy-start sandbox via self.start()                     │
│  3. Build protocol request                                  │
│  4. Dispatch to backend                                     │
│  5. Map raw result to ExecutionResult                       │
└──────────┬──────────────────────────────────────────────────┘
           │
           │  build_python_request(code, working_dir, limits)
           ▼
┌─────────────────────────────────────────────────────────────┐
│  PythonExecutionRequest (Pydantic)           protocol.py    │
│                                                             │
│  {                                                          │
│    "protocol_version": 1,                                   │
│    "code": "x = 5\nx + 1",                                 │
│    "working_dir": "/workspace",                             │
│    "max_output_chars": 50000,                               │
│    "max_value_repr_chars": 10000                            │
│  }                                                          │
└──────────┬──────────────────────────────────────────────────┘
           │
           │  backend.run(("python", "-u", "-c", BOOTSTRAP), stdin_text=json)
           ▼
┌─────────────────────────────────────────────────────────────┐
│  ModalBackend._execute()                 modal_backend.py   │
│                                                             │
│  1. sandbox.exec(*cmd, timeout=N, text=True)                │
│  2. Write JSON request to process stdin                     │
│  3. process.stdin.write_eof() + drain()                     │
│  4. process.wait() for exit code                            │
│  5. Read stdout and stderr                                  │
│  6. Return BackendCommandResult                             │
│                                                             │
│  On timeout: catch ExecTimeoutError, safe-read partial      │
│  output, return result with timed_out=True                  │
└──────────┬──────────────────────────────────────────────────┘
           │
           │  ─── crosses network boundary into Modal sandbox ───
           ▼
┌─────────────────────────────────────────────────────────────┐
│  PYTHON_RUNNER_BOOTSTRAP              python_runner.py      │
│  (runs inside the sandbox as a standalone Python script)    │
│                                                             │
│  1. Read JSON from stdin                                    │
│  2. Validate protocol_version == 1                          │
│  3. cd to working_dir                                       │
│  4. Set up TruncatingBuffer for stdout/stderr capture       │
│  5. AST-parse user code                                     │
│  6. split_last_expression():                                │
│     ┌─────────────────────────────────────┐                 │
│     │  Input:  "x = 5\nx + 1"            │                 │
│     │                                     │                 │
│     │  AST parse → Module with 2 nodes:   │                 │
│     │    [0] Assign: x = 5                │                 │
│     │    [1] Expr: x + 1   ← last expr   │                 │
│     │                                     │                 │
│     │  Output:                            │                 │
│     │    module = Module([Assign(x=5)])    │                 │
│     │    tail   = Expression(x + 1)       │                 │
│     └─────────────────────────────────────┘                 │
│  7. exec(compile(module)) in fresh namespace                │
│  8. eval(compile(tail)) → value                             │
│  9. value_repr = repr(value), clamped to limit              │
│  10. Write JSON response to stdout                          │
│                                                             │
│  On exception: capture type, message, traceback             │
│  On protocol error: emit runner_error response, exit 70     │
└──────────┬──────────────────────────────────────────────────┘
           │
           │  stdout JSON response
           ▼
┌─────────────────────────────────────────────────────────────┐
│  PythonExecutionResponse (Pydantic)          protocol.py    │
│                                                             │
│  {                                                          │
│    "protocol_version": 1,                                   │
│    "success": true,                                         │
│    "runner_error": false,                                   │
│    "stdout": "",                                            │
│    "stderr": "",                                            │
│    "stdout_truncated": false,                               │
│    "stderr_truncated": false,                               │
│    "value_repr": "6",                                       │
│    "value_repr_truncated": false,                           │
│    "error_type": null,                                      │
│    "error_message": null,                                   │
│    "traceback": null                                        │
│  }                                                          │
└──────────┬──────────────────────────────────────────────────┘
           │
           │  parse_python_response(stdout) + _map_python_result()
           ▼
┌─────────────────────────────────────────────────────────────┐
│  ExecutionResult (Pydantic)                    models.py    │
│                                                             │
│  kind           = "python"                                  │
│  status         = "succeeded"                               │
│  success        = True                                      │
│  value_repr     = "6"                                       │
│  stdout         = ""                                        │
│  stderr         = ""                                        │
│  exit_code      = 0                                         │
│  session_id     = "a1b2c3..."                               │
│  sandbox_id     = "sb-xyz..."                               │
│  duration_seconds = 0.42                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Shell Execution Flow

Shell execution is simpler — no IPC protocol, just direct command execution.

```
   Agent / User Code
          │
          │  session.run_shell("ls -la /workspace")
          ▼
┌─────────────────────────────────────────────────────────────┐
│  SandboxSession.run_shell()                     session.py  │
│                                                             │
│  1. Acquire lock                                            │
│  2. Lazy-start sandbox                                      │
│  3. Build shell command:                                    │
│     ("/bin/bash", "-lc", "cd '/workspace' && ls -la ...")   │
│  4. backend.run(shell_command, timeout=N)                   │
└──────────┬──────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│  ModalBackend._execute()                 modal_backend.py   │
│                                                             │
│  1. sandbox.exec("/bin/bash", "-lc", "cd ... && ls -la")    │
│  2. No stdin needed (stdin_text=None)                       │
│  3. wait() → exit_code                                      │
│  4. Read stdout + stderr directly                           │
│  5. Return BackendCommandResult                             │
└──────────┬──────────────────────────────────────────────────┘
           │
           │  _map_shell_result()
           ▼
┌─────────────────────────────────────────────────────────────┐
│  ExecutionResult                               models.py    │
│                                                             │
│  kind     = "shell"                                         │
│  status   = "succeeded" | "failed" | "timed_out"            │
│  success  = (exit_code == 0)                                │
│  stdout   = "total 4\ndrwxr-xr-x ..."                      │
│  stderr   = ""                                              │
│  exit_code = 0                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Session Lifecycle

A session manages sandbox lifecycle through four states:

```
                   ┌─────────────┐
                   │   Created   │
                   │  (idle)     │
                   └──────┬──────┘
                          │  start() / run_python() / run_shell()
                          │  (lazy — first call triggers sandbox creation)
                          ▼
                   ┌─────────────┐
            ┌─────│   Started    │─────┐
            │     │  (running)   │     │
            │     └──────┬──────┘     │
            │            │            │
   detach() │            │ close()    │ run_python()
            │            │            │ run_shell()
            ▼            ▼            │ (reuse sandbox)
     ┌───────────┐ ┌───────────┐     │
     │ Detached  │ │  Closed   │     │
     │           │ │           │◄────┘
     │ sandbox   │ │ sandbox   │   (only on explicit close)
     │ keeps     │ │ terminated│
     │ running   │ │           │
     └───────────┘ └───────────┘
            │
            │  SandboxSession.attach(sandbox_id, config)
            ▼
     ┌───────────────┐
     │  New Session   │
     │  (reattached   │
     │   to running   │
     │   sandbox)     │
     └───────────────┘
```

**Key behaviors:**
- **Lazy start**: The sandbox is not created until the first `start()`, `run_python()`, or `run_shell()` call
- **Sandbox reuse**: Multiple `run_python()` / `run_shell()` calls reuse the same sandbox
- **Detach**: Releases the session's connection but keeps the sandbox alive on Modal's infrastructure
- **Attach**: Creates a new session connected to an existing sandbox via its ID
- **Close**: Terminates the sandbox and marks the session as unusable
- **Thread safety**: All methods acquire a lock before operating (RLock for sync, asyncio.Lock for async)

---

## Error Handling Flow

The library distinguishes between execution failures (user code errors) and infrastructure failures.

```
   Exception occurs
          │
          ├── Inside user code (in sandbox)
          │   └── Captured by bootstrap script
          │       └── Returned as ExecutionResult with:
          │           status = FAILED
          │           error_type = "ValueError" (etc.)
          │           error_message = "..."
          │           traceback = "Traceback (most recent call last)..."
          │
          ├── Bootstrap protocol error
          │   └── runner_error = true in JSON response
          │       └── Mapped to status = BACKEND_ERROR
          │           If exit_code was 0 → raises ProtocolError
          │
          ├── Command timeout (ExecTimeoutError)
          │   └── Caught by ModalBackend._execute()
          │       └── Partial stdout/stderr safely read
          │           └── Returned as ExecutionResult with:
          │               status = TIMED_OUT
          │               timed_out = True
          │
          ├── Modal infrastructure error (modal.Error)
          │   └── Raised as BackendError (or SandboxStartupError)
          │
          └── Session misuse (closed/detached)
              └── Raised as SessionClosedError / SessionDetachedError
```

Tool wrappers (`PythonSandboxTool`, etc.) catch `AgentSandboxError` and convert it to an `ExecutionResult.backend_error()` so agents always receive a structured response rather than an unhandled exception.
