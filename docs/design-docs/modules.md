# Module Reference

This document is the quick module map for the current `agent_sandbox` package. Use it when you need to know where behavior lives before reading source.

## Core runtime

- `src/agent_sandbox/config.py`
  Purpose: validates sandbox config, network policy, resource controls, and artifact-capture limits.
  Key models: `ModalSandboxConfig`, `NetworkPolicy`, `NetworkMode`.
- `src/agent_sandbox/models.py`
  Purpose: shared contract models for runs, sessions, and artifacts.
  Key models: `ExecutionResult`, `SandboxHandle`, `SessionInfo`, `ArtifactMetadata`, `ArtifactPreview`.
- `src/agent_sandbox/exceptions.py`
  Purpose: stable exception hierarchy for config, lifecycle, backend, artifact, and persisted-state failures.
- `src/agent_sandbox/session.py`
  Purpose: canonical sync and async session APIs, lifecycle tracking, run sequencing, artifact capture, preview, and download.
- `src/agent_sandbox/tool.py`
  Purpose: thin tool-call wrappers over the session APIs for host applications or agent registries.

## Execution protocol

- `src/agent_sandbox/execution/protocol.py`
  Purpose: versioned Pydantic request/response models for Python execution.
- `src/agent_sandbox/execution/python_runner.py`
  Purpose: bootstrap code injected into the sandbox for structured Python execution and tail-expression capture.

## Modal backend boundary

- `src/agent_sandbox/backend/base.py`
  Purpose: sync/async backend protocols plus `BackendCommandResult`.
- `src/agent_sandbox/backend/modal_backend.py`
  Purpose: the only Modal-specific layer. Owns App lookup, sandbox create/from_id, process exec, artifact file I/O, and resource kwargs.

## Cross-process orchestration

- `src/agent_sandbox/state.py`
  Purpose: JSON-backed local state store for sessions and runs.
- `src/agent_sandbox/manager.py`
  Purpose: thin orchestration layer that re-attaches stored sandboxes and records run/artifact metadata for CLI or HTTP use.

## Operator surfaces

- `src/agent_sandbox/diagnostics.py`
  Purpose: startup validation for Modal installation and credential discoverability.
- `src/agent_sandbox/cli.py`
  Purpose: non-interactive operator interface for `doctor`, `session`, `run`, `artifact`, and `serve`.
- `src/agent_sandbox/server/`
  Purpose: optional FastAPI transport over the manager/state layer. This package must remain optional and must not leak into the core import path.

## Testing support

- `tests/fakes.py`
  Purpose: deterministic fake backends for session/manager/unit tests.
- `tests/test_artifacts.py`
  Purpose: run metadata, artifact preview/download, and path-safety coverage.
- `tests/test_state.py`
  Purpose: persisted session/run round-trip coverage.
- `tests/test_manager.py`
  Purpose: cross-process reattach behavior and metadata preservation.
- `tests/test_cli.py`
  Purpose: JSON output and exit-code behavior for the CLI.
- `tests/test_diagnostics.py`
  Purpose: environment-safe diagnostics behavior.
- `tests/test_server.py`
  Purpose: optional HTTP route behavior, state-dir wiring, and error mapping. Skips when server deps are not installed.
