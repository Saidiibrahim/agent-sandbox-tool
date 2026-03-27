# Library Charter

## Problem

Agent runtimes often need a safe way to execute untrusted code without moving the entire agent into an isolated environment. This repository provides that execution boundary for Python and shell workloads using Modal sandboxes.

## Primary Users

- Developers embedding sandbox execution into existing agent loops
- Agent framework authors who need typed sync and async execution surfaces
- Security-conscious teams that want the host process to retain secrets and state

## User Value

After integrating this library, a host application can start a sandbox, run Python or shell commands remotely, and receive structured results without giving the sandbox authority over host credentials or orchestration state.

## Non-Goals

- Building a full agent framework
- Managing long-lived workspaces, file sync, or notebook semantics
- Supporting multiple backend providers before the Modal boundary is stable

## Product Constraints

- Network access is blocked by default.
- Results must stay structured and typed.
- Sync and async APIs should remain behaviorally aligned.
- Backend details should stay inside `src/agent_sandbox/backend/`.
