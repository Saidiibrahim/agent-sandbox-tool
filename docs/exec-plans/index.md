# Execution Plans Index

Use this directory for durable task tracking.

- Active work: [active/README.md](./active/README.md)
- Template: [PLAN_TEMPLATE.md](./PLAN_TEMPLATE.md)
- Ongoing debt: [tech-debt-tracker.md](./tech-debt-tracker.md)

## Active Initiatives

- None. See [active/README.md](./active/README.md).

## Completed Initiatives

- [Senior feedback productionization](./completed/senior-feedback-productionization/PLAN_senior-feedback-productionization.md)
- [Harness knowledge migration](./completed/harness-knowledge-migration/PLAN_harness-knowledge-migration.md)

## Workflow Rules

1. Active work uses one `PLAN_<initiative>.md` and one `state/` directory.
2. `state/feature-list.json` is the checklist of record.
3. Markdown task files are deprecated by default.
4. Run `./scripts/execplan/check.sh` before closure.
