# Reliability

Reliability in this repository means predictable sandbox lifecycle behavior and trustworthy execution results.

## Reliability expectations

- Session lifecycle transitions must stay explicit: created, active, detached, terminated.
- Python execution must continue to use structured protocol parsing rather than ad hoc stdout parsing.
- Timeout, detach, close, and reattach behavior should remain covered by deterministic tests.
- Integration tests are the proof path for real Modal behavior, but unit tests must remain sufficient for day-to-day development.

## Required verification

- `pytest -m "not integration"` for normal changes
- `MODAL_RUN_INTEGRATION=1 pytest -m integration` when backend/runtime behavior changes and credentials are available
- `./scripts/execplan/check.sh` when docs or planning state changes

Document any known verification gap in the relevant exec plan or progress log instead of silently skipping it.
