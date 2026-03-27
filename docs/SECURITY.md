# Security

This library executes untrusted code. Security choices are product behavior, not implementation detail.

## Non-negotiable defaults

- Outbound network access is blocked by default.
- Agent state, credentials, and orchestration stay outside the sandbox.
- Modal-specific secret mounting should remain explicit and reviewed.

## Security-sensitive change areas

- `src/agent_sandbox/config.py`
- `src/agent_sandbox/backend/modal_backend.py`
- `src/agent_sandbox/session.py`
- integration tests that prove network, detach, or lifecycle behavior

## Review expectations

- Call out any relaxation of network policy or secret handling in the plan and final change summary.
- Add or update tests when changing lifecycle or security behavior.
- Keep docs and code synchronized so agents do not infer weaker guarantees than the repository intends.
