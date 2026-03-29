# Migrate Repository Knowledge To Canonical Harness Layout

This plan is a living document. Keep `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` current as work proceeds. Maintain this file in accordance with [docs/PLANS.md](../../../PLANS.md).

## Purpose / Big Picture

The repository should be self-sufficient for coding agents. After this migration, agents can start from a concise routing file, follow canonical docs for architecture and product intent, and use a durable exec-plan system that stores implementation state in JSON rather than ad hoc markdown task files.

## Surprises & Discoveries

- Observation: The repo did not contain legacy hidden planning directories or legacy spec directories, so the migration was a bootstrap rather than a content conversion from old plan trees.
  Evidence: `rg --files -uu .` showed only the existing docs and source tree before migration.
- Observation: The repo did not have a database schema, so the generated schema artifact needed to be sourced from the current typed Pydantic models instead of a SQL database.
  Evidence: The package only exposes typed config, execution, and result models under `src/agent_sandbox/`.
- Observation: Repo health gates beyond the migration scope already had baseline issues in existing Python sources.
  Evidence: `ruff check .` reported pre-existing style and upgrade findings in `src/` and `tests/`, and `mypy src` reported existing typing issues in `execution/protocol.py`, `backend/modal_backend.py`, and `session.py`.

## Decision Log

- Decision: Move the existing tracked docs with `git mv` into `design-docs`, `references`, and the root `ARCHITECTURE.md`.
  Rationale: Preserve file history while establishing the canonical layout required by the harness-style knowledge system.
  Date/Author: 2026-03-27 / Codex
- Decision: Record this migration as a completed exec plan and leave `docs/exec-plans/active/` empty after closure.
  Rationale: The work was substantial enough to deserve a durable record, but it is complete at the end of this run.
  Date/Author: 2026-03-27 / Codex
- Decision: Generate `docs/generated/db-schema.md` from Pydantic model schemas.
  Rationale: The repo has no relational schema, but it does have typed schema sources that agents need for protocol and config work.
  Date/Author: 2026-03-27 / Codex

## Outcomes & Retrospective

The repo now has a canonical docs tree, a concise `AGENTS.md`, a durable exec-plan workflow, and mechanical checks for JSON state, legacy path regressions, and markdown link validity. No active initiative remains open after the migration. The main follow-up risks are drift in the new docs system and the pre-existing Ruff/MyPy baseline issues that remain outside this docs-focused migration.

## Context and Orientation

Before this change, the repo had a small `docs/` folder with architecture and testing notes, but no harness-style knowledge layout and no durable in-repo execution planning system. The main code lives under `src/agent_sandbox/`, with `session.py` and `tool.py` as the public API, `backend/` as the Modal boundary, and `execution/` as the protocol/bootstrap layer. The new documentation system adds root routing docs, design and reference indexes, product intent docs, generated schema docs, and an exec-plan tree under `docs/exec-plans/`.

## Plan of Work

First, scaffold the canonical directories and move the tracked docs into their new homes with history-preserving moves. Next, rewrite `AGENTS.md`, add the new root docs, and create the planning workflow documents. Then seed the validator and repo entrypoint scripts, create a completed migration record with JSON state, generate the schema reference from the typed models, and update CI and README references. Finally, run grep sweeps, link checks, and the exec-plan validator to prove the new system is coherent.

## Concrete Steps

Run the following from the repository root.

1. Create the canonical directories and move tracked docs with `git mv`.
2. Add the routing docs, policy docs, planning docs, and validator scripts.
3. Run `python3 -m pip install -e .[dev]` if dependencies are missing.
4. Generate the schema reference with `PYTHONPATH=src ./.venv/bin/python scripts/generate_db_schema.py`.
5. Run `./scripts/execplan/check.sh`.
6. Run `ruff check .`, `ruff format --check .`, `mypy src`, and `pytest -m "not integration"`.

## Machine State

- `state/feature-list.json` is the canonical implementation checklist.
- Every feature starts with `"passes": false`.
- `state/session-state.json` tracks the active feature, blockers, next action, and handoff rules.
- `state/progress.jsonl` is append-only and records meaningful checkpoints with structured evidence.

## Progress

- [x] (2026-03-27T06:20:00Z) Scaffolded the canonical docs tree and moved tracked docs into `ARCHITECTURE.md`, `docs/design-docs/`, and `docs/references/`.
- [x] (2026-03-27T06:35:00Z) Added the routing docs, planning docs, and policy docs required by the canonical knowledge layout.
- [x] (2026-03-27T06:55:00Z) Added exec-plan validation scripts and seeded the completed migration record with JSON state.
- [x] (2026-03-27T07:15:00Z) Generated the typed schema reference, updated repo references, and ran verification sweeps, recording the existing Ruff and MyPy baseline failures separately from the migration outcome.

## Testing Approach

Validation for this migration is repository-governance oriented:

- run `./scripts/execplan/check.sh` and expect the validator, legacy-path scans, and markdown-link checks to pass
- run the legacy hidden-planning-path grep and expect zero tracked-file matches
- run the legacy spec-path grep outside the product-specs directory and expect zero matches
- run `ruff check .`, `ruff format --check .`, `mypy src`, and `pytest -m "not integration"` to separate migration success from any pre-existing repo health issues

## Constraints & Considerations

This migration should stay docs/governance focused. Small script and CI changes are acceptable only when they enforce the JSON-state workflow or generated-doc discipline. The repo must avoid reintroducing hidden planning directories or markdown task files as the default mechanism for durable handoff.
