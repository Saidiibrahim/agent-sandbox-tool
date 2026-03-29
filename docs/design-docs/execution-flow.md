# Execution Flow

This document summarizes the runtime path from host code to a structured result.

## Python execution

1. Host code calls `SandboxSession.run_python()` or `AsyncSandboxSession.run_python()`.
2. The session lazily starts or re-attaches to a sandbox and moves to `active`.
3. The session captures a best-effort manifest of regular files under `working_dir` when artifact capture is enabled.
4. `build_python_request()` creates a versioned JSON request and the backend executes the bootstrap runner as a fresh process inside the sandbox.
5. The runner returns structured stdout/stderr/value/exception data via `PythonExecutionResponse`.
6. The session captures a second manifest, diffs it against the first, and records added/modified artifacts.
7. The mapped `ExecutionResult` includes:
   - `run_id`
   - `sequence_number`
   - `status`
   - `stdout` / `stderr`
   - `value_repr`
   - `artifacts`
   - timestamps and duration

## Shell execution

1. Host code calls `run_shell()`.
2. The session builds `(<shell>, -lc, "cd <working_dir> && <command>")`.
3. The backend executes the shell command as a separate process in the sandbox.
4. The session maps exit status and timeout information into `ExecutionResult`.
5. When artifact capture is enabled, the same before/after manifest diff is applied.

## Session lifecycle

Sessions expose four explicit states:

- `created`
- `active`
- `detached`
- `terminated`

Important semantics:

- `detach()` drops the local connection but keeps the remote sandbox alive
- `attach()` reconstructs a session handle from `sandbox_id`
- filesystem state persists within a sandbox session
- Python interpreter globals do not persist between `run_python()` calls because each execution uses a fresh process

## Cross-process reuse

The library stays daemon-free. Cross-process reuse is handled by:

- `LocalStateStore` for JSON-backed session/run persistence
- `SandboxManager` for re-attach, run, list, artifact preview, and download flows used by the CLI and optional server

## Artifact access

Artifacts are best-effort metadata for files added or modified under `working_dir` during a run.

Implemented behaviors:

- per-run metadata capture
- text preview while the sandbox remains alive
- local download while the sandbox remains alive

Non-goals for the current design:

- durable artifact persistence after sandbox termination
- deleted-file tracking
- background artifact sync
