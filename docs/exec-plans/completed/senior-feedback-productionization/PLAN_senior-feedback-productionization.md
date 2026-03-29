# Productionize Senior Feedback Roadmap

This plan is a living document. Keep `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` current as work proceeds. Maintain this file in accordance with [docs/PLANS.md](../../../PLANS.md).

## Purpose / Big Picture

The repo should move from a strong Modal MVP to a production-evaluable library and operator tool. After this initiative, the library should expose richer lifecycle and artifact semantics, support persisted attach/reuse across processes, ship a stable CLI, optionally expose a thin HTTP surface, and have packaging/docs/CI that prove another team can install and trust it.

## Surprises & Discoveries

- Observation: The improved checkout is not a drop-in sync because it assumes new state, manager, CLI, diagnostics, and server layers plus broader models and session semantics.
  Evidence: `diff -rq . /Users/ibrahimsaidi/Downloads/agent-sandbox-tool --exclude .git --exclude .venv --exclude __pycache__` showed new modules and changed contracts across `config.py`, `models.py`, `session.py`, `backend/base.py`, and `backend/modal_backend.py`.
- Observation: The current repo governance gate already fails before this initiative begins.
  Evidence: `./scripts/execplan/check.sh` reported `Broken local markdown links detected: docs/exec-plans/completed/harness-knowledge-migration/PLAN_harness-knowledge-migration.md: missing link target ../../PLANS.md`.
- Observation: The current runtime baseline is healthy when run with `src/` on `PYTHONPATH`, but raw `pytest` without an editable install only proves import-path setup problems.
  Evidence: `PYTHONPATH=src pytest -m "not integration"` passed with `9 passed, 2 deselected`, while plain `pytest -m "not integration"` failed during collection with `ModuleNotFoundError: No module named 'agent_sandbox'`.
- Observation: The improved CLI/diagnostics tests are environment-sensitive as written.
  Evidence: Subagent planning run against the improved checkout reported that `tests/test_cli.py` and `tests/test_diagnostics.py` fail when Modal is already installed/configured locally.
- Observation: FastAPI treated the injected `manager` as a query parameter when the route handlers relied on postponed `Annotated[..., Depends(...)]` dependency metadata inside the app factory.
  Evidence: `.venv/bin/pytest -m "not integration"` initially failed with `422` responses containing `{"loc":["query","manager"]}` for `/runs` and artifact routes; switching to a concrete `manager_dependency = Depends(get_manager)` object resolved the failures and the same routes returned `200/404` under a direct `TestClient` probe.
- Observation: Real Modal timeouts do not reliably raise `ExecTimeoutError`; under the current Modal baseline they can return `exit_code == -1` with empty Python-runner stdout.
  Evidence: `MODAL_RUN_INTEGRATION=1 .venv/bin/pytest -m integration` initially failed because the timeout path reached `parse_python_response()` with empty stdout instead of returning `ExecutionStatus.TIMED_OUT`.
- Observation: The first persisted-state implementation was not safe for concurrent reuse because it updated session JSON with a stale read-modify-write cycle and a shared temp filename.
  Evidence: A concurrent `SandboxManager.run_python()` repro produced `StateStoreError` on `sess-1.json.tmp`, and the stored `run_count`/`last_run_id` could race even when both runs succeeded.

## Decision Log

- Decision: Implement the productionization work in phased slices instead of copying the improved checkout wholesale.
  Rationale: The improved checkout omits this repo’s docs/governance layer and does not add enough tests for the optional server slice.
  Date/Author: 2026-03-27 / Codex
- Decision: Fix the broken exec-plan link as part of the initiative bootstrap before relying on `./scripts/execplan/check.sh`.
  Rationale: The repo requires the exec-plan validator before closing planning or docs work, so the baseline must be repaired early.
  Date/Author: 2026-03-27 / Codex
- Decision: Treat the optional FastAPI service as part of the initiative only if it lands with route tests and HTTP exception mapping.
  Rationale: Several planning passes agreed the improved server slice is directionally correct but under-tested and incomplete on error semantics.
  Date/Author: 2026-03-27 / Codex
- Decision: Preserve repo-specific docs/governance surfaces while expanding runtime/operator features.
  Rationale: The improved README/CI remove local governance visibility, which would be a regression in this repository.
  Date/Author: 2026-03-27 / Codex
- Decision: Use a concrete FastAPI dependency object for `SandboxManager` injection instead of postponed `Annotated[..., Depends(...)]` route annotations in the nested app factory.
  Rationale: In this repo’s app-factory shape, FastAPI was resolving the `Annotated` dependency as request input on several GET routes, producing `422` responses until the dependency object was bound directly.
  Date/Author: 2026-03-27 / Codex
- Decision: Treat Modal's `exit_code == -1` plus `ExecTimeoutError` sentinel as a timed-out execution result instead of a protocol failure.
  Rationale: The live backend can surface timeouts through the process result rather than an exception, so the library contract must normalize both paths to `ExecutionStatus.TIMED_OUT`.
  Date/Author: 2026-03-29 / Codex
- Decision: Reject `ephemeral_disk_mb` under the current package baseline instead of silently accepting a no-op resource control.
  Rationale: Modal 1.4.0 ignores sandbox ephemeral disk for this flow, so advertising it as active would be a misleading contract.
  Date/Author: 2026-03-29 / Codex
- Decision: Serialize persisted session updates with per-session file locks and unique temp files.
  Rationale: The manager/state layer is explicitly the daemon-free cross-process reuse mechanism, so lost updates and temp-file collisions are correctness bugs, not best-effort behavior.
  Date/Author: 2026-03-29 / Codex

## Outcomes & Retrospective

Implemented and closed the productionization slice described by the senior feedback without replacing the repo’s governance layer. The repo now has richer config/models/exceptions, resource-aware Modal backend behavior, durable state/manager orchestration, a tested CLI, an optional tested FastAPI service, updated docs/schema/CI, and packaging metadata that supports console-script and wheel smoke validation. The follow-up hardening pass fixed the live Modal timeout regression, serialized persisted state updates for concurrent reuse, stabilized diagnostics/CLI lifecycle semantics and `serve` state-dir wiring, and made unsupported ephemeral disk controls fail fast instead of overpromising. Final verification passed with `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`, `.venv/bin/mypy src`, `.venv/bin/pytest -m "not integration"`, `MODAL_RUN_INTEGRATION=1 .venv/bin/pytest -m integration`, `.venv/bin/python -m build`, `./scripts/execplan/check.sh`, and `.venv/bin/agent-sandbox --help`.

## Context and Orientation

The current public surface lives in `src/agent_sandbox/session.py` and `src/agent_sandbox/tool.py`, with execution protocol logic under `src/agent_sandbox/execution/` and Modal-specific behavior isolated in `src/agent_sandbox/backend/`. The repo already has sync and async sessions, typed results, fake backends, docs routing, and JSON-state exec-plan governance. The improved checkout at `/Users/ibrahimsaidi/Downloads/agent-sandbox-tool` adds richer config/models, artifact tracking, persisted local state, a thin manager, CLI, diagnostics, optional FastAPI service, packaging updates, and broader tests. The main task is to port those capabilities without regressing the repo’s architecture boundaries, docs system, or validation gates.

## Plan of Work

First, bootstrap the initiative and repair the broken exec-plan link so governance checks are usable again. Next, expand the shared runtime contracts in `config.py`, `models.py`, and `exceptions.py`, then extend the backend protocols and Modal backend with resource controls plus artifact file read/download support. After that, upgrade `session.py` to record lifecycle metadata, run IDs, sequence numbers, and artifact manifests for both sync and async sessions, hardening the improved design where needed for path normalization and attach/reattach semantics. Then add `state.py` and `manager.py` so detached sandbox IDs and recorded runs become durable across CLI or service invocations. On top of that foundation, add `diagnostics.py` and a stable `cli.py` with JSON mode, predictable exit codes, and artifact/session/run commands. If the HTTP service ships in this initiative, add the optional `server/` package with explicit error mapping and direct route tests. Finish by updating packaging, docs, schema references, and CI so the broader operator surface is reflected in install/build/test workflows without removing repo-specific governance checks.

## Concrete Steps

Run the following from the repository root.

1. Bootstrap the active initiative under `docs/exec-plans/active/senior-feedback-productionization/` and repair the broken historical plan link.
2. Run `PYTHONPATH=src pytest -m "not integration"` and `./scripts/execplan/check.sh` to keep the baseline evidence fresh.
3. Port the contract and runtime slices in `src/agent_sandbox/` and extend the fakes/tests to cover lifecycle, artifact, and persisted-state behavior.
4. Add CLI and diagnostics, then optionally add the server package if route tests land in the same wave.
5. Update `pyproject.toml`, `README.md`, architecture/testing docs, generated schema docs, and CI.
6. Run `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -m "not integration"`, `python3 -m build`, wheel smoke checks, `./scripts/execplan/check.sh`, and `MODAL_RUN_INTEGRATION=1 pytest -m integration` when credentials are available.

## Machine State

- `state/feature-list.json` is the canonical implementation checklist.
- Every feature starts with `"passes": false`.
- `state/session-state.json` tracks the active feature, blockers, next action, and handoff rules.
- `state/progress.jsonl` is append-only and records meaningful checkpoints with structured evidence.

## Progress

- [x] (2026-03-27T06:26:49Z) Read the repo guardrails, architecture docs, planning docs, current implementation, and the improved checkout to build a concrete gap map.
- [x] (2026-03-27T06:26:49Z) Spawned six planning subagents and collected reviewed recommendations across contracts, session/backend/artifacts, CLI/state/manager, server, and packaging/docs/CI.
- [x] (2026-03-27T06:26:49Z) Repaired the broken exec-plan link, created the active initiative, and revalidated the governance and unit-test baseline.
- [x] (2026-03-27T06:26:49Z) Ported the core runtime contract slice across config/models/exceptions/backend/session and verified the expanded non-integration suite.
- [x] (2026-03-27T06:26:49Z) Added persisted state and manager layers with created-at preservation across reattach flows.
- [x] (2026-03-27T06:59:23Z) Added diagnostics and the manager-backed CLI with stable JSON/exit-code behavior plus environment-safe tests.
- [x] (2026-03-27T06:59:23Z) Shipped the optional FastAPI service with direct route tests, explicit HTTP exception mapping, and corrected dependency wiring.
- [x] (2026-03-27T06:59:23Z) Updated packaging/docs/CI, regenerated schema docs, and ran the full local verification bundle including wheel smoke checks.
- [x] (2026-03-27T08:00:00Z) Synced reliability/testing/design docs and exec-plan state with the current implementation reality, keeping the initiative active because live Modal integration still fails on the timeout path.
- [x] (2026-03-29T04:24:06Z) Fixed the live Modal timeout mapping, persisted-state concurrency gaps, diagnostics/CLI stability issues, and `serve` state-dir seam, then reran the full verification bundle and moved the initiative to `completed/`.

## Testing Approach

Validation is phase-based:

- Baseline and planning: `PYTHONPATH=src pytest -m "not integration"` and `./scripts/execplan/check.sh`
- Core runtime: targeted unit tests for config, session, async session, tool, artifacts, state, manager, diagnostics, and CLI as those slices land
- Packaging and installability: `python3 -m build`, wheel install smoke, console-script smoke, and `py.typed` wheel-content verification
- Optional server: direct route tests plus a local `uvicorn` smoke check only if the server slice ships
- Live Modal behavior: `MODAL_RUN_INTEGRATION=1 pytest -m integration` once credentials are available; treat a failure as a blocking product gap to record in the active exec plan

If any verification remains unrun, record the exact gap in `Progress`, `Decision Log`, and `state/progress.jsonl`.

## Constraints & Considerations

Preserve the library-first boundary described in `ARCHITECTURE.md`: core modules should not take hard dependencies on FastAPI or CLI concerns. Keep network blocked by default. Do not remove repo-specific docs/governance references while expanding README or CI. Treat the improved checkout as source material, not authority: harden artifact path handling, avoid environment-coupled tests, and do not ship the optional server without route tests and HTTP exception mapping. Keep the current baseline distinction explicit between real regressions and environment/setup noise.
