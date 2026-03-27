# Generated Schema Reference

This repository does not define a relational database schema. This generated file documents the current typed schema sources that act as the authoritative machine-readable contract for config, protocol, and execution results.

## Regeneration

Run from the repository root after installing dependencies:

```bash
PYTHONPATH=src ./.venv/bin/python scripts/generate_db_schema.py
```

## Configuration

## ModalSandboxConfig

- Domain: Configuration

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| app_name | string | no | default="agent-sandbox" |
| python_version | string | no | default="3.11" |
| python_packages | array<string> | no | - |
| timeout_seconds | integer | no | default=1800 |
| idle_timeout_seconds | integer | null | no | default=300 |
| default_exec_timeout_seconds | integer | no | default=120 |
| working_dir | string | no | default="/workspace" |
| shell_executable | string | no | default="/bin/bash" |
| max_output_chars | integer | no | default=50000 |
| max_value_repr_chars | integer | no | default=10000 |
| network | NetworkPolicy | no | - |
| verbose | boolean | no | default=false |
| image | unknown | null | no | default=null |
| secrets | array<unknown> | no | - |
| tags | object | no | - |

### Referenced Definitions

- `NetworkMode`: enum
- `NetworkPolicy`: object

## NetworkPolicy

- Domain: Configuration

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| mode | NetworkMode | no | default="blocked" |
| cidr_allowlist | array<string> | no | - |

### Referenced Definitions

- `NetworkMode`: enum

## Execution Protocol

## PythonExecutionRequest

- Domain: Execution Protocol

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| protocol_version | integer | no | default=1 |
| code | string | yes | - |
| working_dir | string | null | no | default=null |
| max_output_chars | integer | no | default=50000 |
| max_value_repr_chars | integer | no | default=10000 |

## PythonExecutionResponse

- Domain: Execution Protocol

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| protocol_version | integer | no | default=1 |
| success | boolean | yes | - |
| runner_error | boolean | no | default=false |
| stdout | string | no | default="" |
| stderr | string | no | default="" |
| stdout_truncated | boolean | no | default=false |
| stderr_truncated | boolean | no | default=false |
| value_repr | string | null | no | default=null |
| value_repr_truncated | boolean | no | default=false |
| error_type | string | null | no | default=null |
| error_message | string | null | no | default=null |
| traceback | string | null | no | default=null |

## Shared Models

## SandboxHandle

- Domain: Shared Models

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| session_id | string | yes | - |
| sandbox_id | string | yes | - |
| app_name | string | yes | - |
| working_dir | string | yes | - |

## ExecutionResult

- Domain: Shared Models

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| kind | ExecutionKind | yes | - |
| status | ExecutionStatus | yes | - |
| success | boolean | yes | - |
| command | array<string> | no | - |
| stdout | string | no | default="" |
| stderr | string | no | default="" |
| stdout_truncated | boolean | no | default=false |
| stderr_truncated | boolean | no | default=false |
| exit_code | integer | null | no | default=null |
| value_repr | string | null | no | default=null |
| value_repr_truncated | boolean | no | default=false |
| error_type | string | null | no | default=null |
| error_message | string | null | no | default=null |
| traceback | string | null | no | default=null |
| session_id | string | yes | - |
| sandbox_id | string | null | no | default=null |
| started_at | string | yes | - |
| completed_at | string | yes | - |
| duration_seconds | number | yes | - |

### Referenced Definitions

- `ExecutionKind`: enum
- `ExecutionStatus`: enum
