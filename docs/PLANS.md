# Plans

Execution plans are the durable task ledger for this repository. Non-trivial work uses one markdown plan narrative plus JSON state files for feature tracking and long-running-agent handoff.

- Index: [docs/exec-plans/index.md](./exec-plans/index.md)
- Tech debt tracker: [docs/exec-plans/tech-debt-tracker.md](./exec-plans/tech-debt-tracker.md)

## Lifecycle

1. Create one initiative directory under `docs/exec-plans/active/`.
2. Create `PLAN_<initiative>.md` from [docs/exec-plans/PLAN_TEMPLATE.md](./exec-plans/PLAN_TEMPLATE.md).
3. Add `state/feature-list.json`, `state/session-state.json`, and `state/progress.jsonl`.
4. Expand the requested outcome into end-to-end feature entries in `state/feature-list.json`, and start every feature with `"passes": false`.
5. Work one feature at a time, keep the markdown plan current, update `state/session-state.json`, and append structured progress entries to `state/progress.jsonl`.
6. Only flip `"passes"` to `true` after evidence-backed verification.
7. Move the initiative directory to `docs/exec-plans/completed/` when the work is closed with proof.

## Canonical State Files

- `PLAN_<initiative>.md`: the durable human-readable narrative
- `state/feature-list.json`: canonical implementation checklist
- `state/session-state.json`: active feature, blockers, next action, and handoff rules
- `state/progress.jsonl`: append-only checkpoint log with evidence

Per-task markdown files are intentionally not part of the default workflow. Keep checklists in `state/feature-list.json`, not in task markdown.

## Validation

Run `./scripts/execplan/check.sh` before closing docs or planning changes. The validator rejects:

- missing required plan sections
- missing JSON state files
- empty feature lists
- invalid feature references in session state or progress logs
- deprecated `tasks/` directories inside exec-plan trees
- legacy hidden planning-path or legacy spec-path regressions
- broken local markdown links

## Weekly Doc Hygiene

This repo expects a weekly doc-gardening pass that checks stale docs, legacy path regressions, and broken local links. The recurring automation should open an inbox item; if automation is unavailable or paused, run the same checks manually and log follow-up work in an exec plan.
