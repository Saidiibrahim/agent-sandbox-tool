# Exec Plan Template

This template is adapted from the OpenAI cookbook guidance on durable ExecPlans and tuned for this repository’s markdown-plan-plus-JSON-state workflow.

# <Short, action-oriented description>

This plan is a living document. Keep `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` current as work proceeds. Maintain this file in accordance with [docs/PLANS.md](../PLANS.md).

## Purpose / Big Picture

Explain what someone gains after this change, why it matters, and how they can observe the result working.

## Surprises & Discoveries

Capture unexpected behaviors, bugs, constraints, or insights discovered during implementation. Include short evidence snippets when possible.

- Observation: ...
  Evidence: ...

## Decision Log

Record every meaningful design or scope decision.

- Decision: ...
  Rationale: ...
  Date/Author: ...

## Outcomes & Retrospective

Summarize outcomes, remaining gaps, and lessons learned at major milestones or when the initiative closes.

## Context and Orientation

Treat the reader as new to the repository. Name the key files and modules by repository-relative path. Define any non-obvious terms immediately and explain how they appear in this repo.

## Plan of Work

Describe the sequence of edits and additions in prose. Name the files and code locations that change, and explain what will be added, moved, or removed.

## Concrete Steps

List the exact commands to run, the working directory, and the expected observable output. Update this section as the work evolves.

## Machine State

Document the machine-readable execution contract for the initiative.

- `state/feature-list.json` is the canonical implementation checklist.
- Every feature starts with `"passes": false`.
- `state/session-state.json` tracks the active feature, blockers, next action, and handoff rules.
- `state/progress.jsonl` is append-only and records meaningful checkpoints with structured evidence.

## Progress

Use checkboxes with timestamps. Every stopping point must be reflected here, including partial completion.

- [ ] Example incomplete step.
- [x] (2026-03-27T06:00:00Z) Example completed step.
- [ ] Example partially complete step (completed: X; remaining: Y).

## Testing Approach

Describe how to validate the work. Include exact commands, expected outcomes, and any environment assumptions. If there is a verification gap, state it explicitly.

## Constraints & Considerations

Document safety constraints, scope boundaries, idempotence or recovery notes, and any repo-specific guardrails that future contributors must preserve.
