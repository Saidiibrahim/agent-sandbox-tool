"""Async session regression tests for result and timeout normalization."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from agent_sandbox.config import ModalSandboxConfig
from agent_sandbox.execution.protocol import PythonExecutionResponse
from agent_sandbox.models import ExecutionStatus
from agent_sandbox.session import AsyncSandboxSession

from .fakes import FakeAsyncBackend, backend_result


@pytest.mark.asyncio
async def test_async_session_maps_python_results() -> None:
    protocol = PythonExecutionResponse(
        success=True, stdout="async\n", value_repr="3"
    ).model_dump_json()
    backend = FakeAsyncBackend(
        queue=[backend_result(stdout=protocol, command=("python", "-u", "-c", "runner"))]
    )
    session = AsyncSandboxSession(ModalSandboxConfig(), backend=backend)

    result = await session.run_python("print('async')\n1 + 2")

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.value_repr == "3"


@pytest.mark.asyncio
async def test_async_session_maps_python_timeout_sentinel() -> None:
    backend = FakeAsyncBackend(
        queue=[
            backend_result(
                exit_code=-1,
                error_type="ExecTimeoutError",
                error_message="Command exceeded timeout of 1 seconds.",
                command=("python", "-u", "-c", "runner"),
            )
        ]
    )
    session = AsyncSandboxSession(ModalSandboxConfig(), backend=backend)

    result = await session.run_python("import time\ntime.sleep(5)", timeout_seconds=1)

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.success is False
    assert result.error_type == "ExecTimeoutError"


@pytest.mark.asyncio
async def test_async_session_maps_python_timeout_error_type_to_timed_out_result() -> None:
    backend = FakeAsyncBackend(
        queue=[
            backend_result(
                stdout="",
                exit_code=137,
                error_type="ExecTimeoutError",
                error_message=(
                    "Command exceeded timeout of 1 seconds. "
                    "Modal returned signal exit code 137 at the execution deadline."
                ),
                command=("python", "-u", "-c", "runner"),
            )
        ]
    )
    session = AsyncSandboxSession(ModalSandboxConfig(), backend=backend)

    result = await session.run_python("import time\ntime.sleep(5)", timeout_seconds=1)

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.success is False
    assert result.error_type == "ExecTimeoutError"
    assert "timeout of 1 seconds" in (result.error_message or "")
    assert result.exit_code is None


@pytest.mark.asyncio
async def test_async_session_maps_missing_payload_with_no_exit_code_to_timed_out_result() -> None:
    started_at = datetime.now(UTC)
    backend = FakeAsyncBackend(
        queue=[
            replace(
                backend_result(
                    stdout="",
                    stderr="",
                    exit_code=None,
                    command=("python", "-u", "-c", "runner"),
                ),
                started_at=started_at,
                completed_at=started_at + timedelta(seconds=1.05),
            )
        ]
    )
    session = AsyncSandboxSession(ModalSandboxConfig(), backend=backend)

    result = await session.run_python("import time\ntime.sleep(5)", timeout_seconds=1)

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.success is False
    assert result.error_type == "ExecTimeoutError"
    assert "without a JSON payload" in (result.error_message or "")
    assert result.exit_code is None
