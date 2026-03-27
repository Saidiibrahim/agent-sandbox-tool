# Design

This repo optimizes for an agent-readable, layered Python library.

- Keep the public API small and typed.
- Keep execution protocol concerns separate from backend concerns.
- Prefer additive, verifiable changes over broad rewrites.
- Document architecture decisions in [design-docs/](./design-docs/index.md) rather than expanding `AGENTS.md`.

When a change affects multiple layers, update `ARCHITECTURE.md`, the relevant design doc, and the matching tests in the same batch.
