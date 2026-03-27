# Agent Sandbox Tool Map

Start here when you need repository context. `AGENTS.md` is a router, not the full policy manual.

## Read Order

1. [ARCHITECTURE.md](./ARCHITECTURE.md)
2. [docs/PLANS.md](./docs/PLANS.md)
3. [docs/exec-plans/index.md](./docs/exec-plans/index.md)
4. Relevant domain docs under `docs/`
5. Source files under `src/agent_sandbox/`
6. Tests under `tests/`

For non-trivial implementation or migration work, read in this order:
1. [docs/exec-plans/PLAN_TEMPLATE.md](./docs/exec-plans/PLAN_TEMPLATE.md)
2. [docs/exec-plans/index.md](./docs/exec-plans/index.md)
3. The initiative plan: `docs/exec-plans/active/<initiative>/PLAN_<initiative>.md`
4. `docs/exec-plans/active/<initiative>/state/session-state.json`
5. `docs/exec-plans/active/<initiative>/state/feature-list.json`
6. `docs/exec-plans/active/<initiative>/state/progress.jsonl`

## Canonical Path Map

- Architecture and package map: [ARCHITECTURE.md](./ARCHITECTURE.md)
- Product intent: [docs/PRODUCT_SENSE.md](./docs/PRODUCT_SENSE.md)
- Product specs: [docs/product-specs](./docs/product-specs)
- Design docs: [docs/design-docs/index.md](./docs/design-docs/index.md)
- Reference material: [docs/references/index.md](./docs/references/index.md)
- Planning standard: [docs/PLANS.md](./docs/PLANS.md)
- Exec-plan template: [docs/exec-plans/PLAN_TEMPLATE.md](./docs/exec-plans/PLAN_TEMPLATE.md)
- Reliability rules: [docs/RELIABILITY.md](./docs/RELIABILITY.md)
- Security rules: [docs/SECURITY.md](./docs/SECURITY.md)
- Quality ledger: [docs/QUALITY_SCORE.md](./docs/QUALITY_SCORE.md)
- Generated schema docs: [docs/generated/db-schema.md](./docs/generated/db-schema.md)

## Routing By Work Type

- Public API or package boundaries: read `ARCHITECTURE.md`, then `src/agent_sandbox/session.py`, `src/agent_sandbox/tool.py`, and `docs/design-docs/modules.md`.
- Modal backend/runtime work: read `src/agent_sandbox/backend/modal_backend.py`, [docs/design-docs/design-decisions.md](./docs/design-docs/design-decisions.md), and [docs/SECURITY.md](./docs/SECURITY.md).
- Python execution/protocol work: read `src/agent_sandbox/execution/`, [docs/design-docs/execution-flow.md](./docs/design-docs/execution-flow.md), and [docs/generated/db-schema.md](./docs/generated/db-schema.md).
- Test or verification work: read [docs/references/testing.md](./docs/references/testing.md) and the matching files in `tests/`.
- Docs/governance work: read [docs/PLANS.md](./docs/PLANS.md), [docs/exec-plans/index.md](./docs/exec-plans/index.md), and [docs/design-docs/core-beliefs.md](./docs/design-docs/core-beliefs.md).

## Working Rules

- Use the `docs/product-specs` directory for specs. Do not introduce legacy top-level spec folders.
- Use `docs/exec-plans/` for durable plans. Do not introduce legacy hidden planning folders.
- Active initiatives use exactly one `PLAN_<initiative>.md` plus `state/feature-list.json`, `state/session-state.json`, and `state/progress.jsonl`.
- `state/feature-list.json` is the canonical implementation checklist. Markdown task files are deprecated by default.
- Run `./scripts/execplan/check.sh` before closing docs or planning changes.

## Core Commands

- Install: `pip install -e .[dev]`
- Lint: `ruff check .`
- Format check: `ruff format --check .`
- Types: `mypy src`
- Fast tests: `pytest -m "not integration"`
- Live Modal tests: `MODAL_RUN_INTEGRATION=1 pytest -m integration`
- Exec-plan validation: `./scripts/execplan/check.sh`
