# Restore E2E Workflow Readiness

This plan is a living document. Keep `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` current as work proceeds. Maintain this file in accordance with [docs/PLANS.md](../../../PLANS.md).

## Purpose / Big Picture

Future developer workflows should be able to trust this repository’s full path from docs validation through live Modal execution. This follow-up closed the two remaining blockers from the last live verification pass: a broken historical exec-plan link that kept the validator red, and an intermittent live Modal timeout shape that escaped normalization and raised `ProtocolError` instead of returning a structured timed-out result.

## Surprises & Discoveries

- Observation: The intermittent timeout failure is not the already-handled `exit_code == -1` path.
  Evidence: Direct backend reproduction showed Modal sometimes returns `exit_code == 137`, empty stdout, and empty stderr after about `1.38s` for a `timeout_seconds=1` run.

## Decision Log

- Decision: Fix the timeout behavior in `src/agent_sandbox/backend/modal_backend.py` instead of adding a session-level fallback for empty stdout.
  Rationale: The public session contract already maps normalized backend timeout results correctly; the missing behavior is a Modal-specific sentinel that belongs at the backend boundary.
  Date/Author: 2026-03-29 / Codex

## Outcomes & Retrospective

The validator link is repaired and `./scripts/execplan/check.sh` is green again. The live Modal timeout path is now normalized at the backend boundary for the observed `exit_code == 137` deadline kill shape, the public session layer emits richer `ProtocolError` context if a future runner payload goes missing, and both unit plus live coverage now lock the timeout contract more tightly. Final validation passed across lint, format, types, non-integration tests, build, exec-plan validation, manual library/CLI timeout proofs, and three consecutive full live integration runs.

## Context and Orientation

The validator issue was in `docs/exec-plans/completed/senior-feedback-productionization/PLAN_senior-feedback-productionization.md`. The timeout-path contract crosses `src/agent_sandbox/backend/modal_backend.py`, `src/agent_sandbox/session.py`, and `src/agent_sandbox/execution/python_runner.py`, with live coverage in `tests/integration/test_modal_backend.py` and unit coverage in `tests/test_session.py`, `tests/test_async_session.py`, `tests/test_cli.py`, and `tests/test_modal_backend.py`.

## Plan of Work

Repair the broken local markdown link so `./scripts/execplan/check.sh` is green again. Then reproduce the intermittent live timeout failure at the raw backend layer, normalize the real Modal timeout sentinel at the backend boundary, and improve protocol diagnostics so future failures include the raw backend context instead of a context-free parse error. Finally, strengthen timeout regression coverage and rerun the full local plus live verification bundle until the required repeated integration passes hold.

## Concrete Steps

Run the following from the repository root.

1. Reproduce the current timeout-path failure with focused live Modal runs and direct backend probes.
2. Patch the broken markdown link and add the backend normalization plus regression tests.
3. Run `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`, `.venv/bin/mypy src`, `.venv/bin/pytest -m "not integration"`, `.venv/bin/python -m build`, and `./scripts/execplan/check.sh`.
4. Run `MODAL_RUN_INTEGRATION=1 .venv/bin/pytest -m integration` until it passes three consecutive times.
5. Run manual library and CLI timeout proofs and record the exact outputs and exit behavior.

## Machine State

- `state/feature-list.json` is the canonical implementation checklist.
- Every feature starts with `"passes": false`.
- `state/session-state.json` tracks the active feature, blockers, next action, and handoff rules.
- `state/progress.jsonl` is append-only and records meaningful checkpoints with structured evidence.

## Progress

- [x] (2026-03-29T06:15:51Z) Read the repo guardrails, planning docs, timeout-path code, and live integration test target.
- [x] (2026-03-29T06:15:51Z) Reproduced the intermittent live Modal timeout failure and captured the missing backend sentinel shape (`exit_code == 137`, empty stdout/stderr, elapsed past timeout).
- [x] (2026-03-29T06:26:42Z) Repaired the broken exec-plan link, tightened the Modal timeout normalization to the observed backend sentinel, and added regression coverage across backend, session, CLI, python-runner, and live integration paths.
- [x] (2026-03-29T06:26:42Z) Ran the full required validation bundle, manual developer-workflow proofs, and three consecutive full live integration passes.

## Testing Approach

Validation included the full required bundle from the user request, plus repeated live Modal timeout runs until the structured timeout result stayed stable under repetition. Any renewed `ProtocolError` on missing runner payload should now include raw backend context in the exception message for faster diagnosis.

## Constraints & Considerations

The blocked-by-default network policy stayed unchanged. The fresh-process-per-exec model stayed unchanged. Timeout normalization now happens at the backend contract boundary for the observed Modal runtime sentinel instead of being hidden in tests alone, and the CLI plus Python API remain aligned on structured timeout behavior.
