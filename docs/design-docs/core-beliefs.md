# Core Beliefs

These are the operating assumptions behind this repository’s agent-facing knowledge system.

## Repository-Local Knowledge Wins

If a coding agent cannot find a decision in the repository, that decision effectively does not exist during execution. Important architecture, product intent, and planning state must live in versioned repo files.

## `AGENTS.md` Is A Router

`AGENTS.md` should stay short. It points agents toward the right canonical docs instead of trying to encode every policy inline.

## Plans Are Durable, State Is Structured

The human-readable story of a non-trivial initiative belongs in one markdown plan. The implementation checklist and session handoff data belong in JSON state files that are easier to validate mechanically.

## Evidence Beats Guessing

A feature is not complete because code was written. It is complete when the plan, state, and verification evidence all agree that the behavior works.

## Security Defaults Must Stay Visible

This library exists to run untrusted code. Security-sensitive defaults such as blocked network access and host-owned secrets must remain explicit in docs, code, and tests.
