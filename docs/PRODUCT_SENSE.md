# Product Sense

`agent-sandbox-tool` should stay narrow, composable, and security-conscious.

## What good looks like

- A host application can execute untrusted Python or shell code remotely through a small typed API.
- Consumers can reason about success, failure, timeouts, and backend faults from structured results.
- The sandbox boundary is obvious in both code and docs.

## What to resist

- Turning the library into a full orchestration framework
- Smuggling Modal-specific concepts into public APIs without a strong need
- Relaxing security defaults for convenience without explicit documentation and tests

## Decision heuristic

If a change makes the public API larger, ask whether it improves the host-controlled execution contract or just expands surface area. Default to smaller surfaces, clearer boundaries, and better evidence.
