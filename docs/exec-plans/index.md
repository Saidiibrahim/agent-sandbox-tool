# Execution Plans Index

Use this directory for durable task tracking.

- Active work: [active/README.md](./active/README.md)
- Template: [PLAN_TEMPLATE.md](./PLAN_TEMPLATE.md)
- Ongoing debt: [tech-debt-tracker.md](./tech-debt-tracker.md)

## Active Initiatives

There are currently no active initiatives in `docs/exec-plans/active/` beyond the README placeholder. Start new non-trivial work there using the template and JSON state trio.

## Completed Initiatives

- [Harness knowledge migration](./completed/harness-knowledge-migration/PLAN_harness-knowledge-migration.md)

## Workflow Rules

1. Active work uses one `PLAN_<initiative>.md` and one `state/` directory.
2. `state/feature-list.json` is the checklist of record.
3. Markdown task files are deprecated by default.
4. Run `./scripts/execplan/check.sh` before closure.
