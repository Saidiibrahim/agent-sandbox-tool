"""Sync session regression tests for lifecycle and result mapping semantics."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from agent_sandbox.config import ModalSandboxConfig
from agent_sandbox.exceptions import ProtocolError
from agent_sandbox.execution.protocol import PythonExecutionResponse
from agent_sandbox.models import ExecutionStatus
from agent_sandbox.session import SandboxSession

from .fakes import FakeBackend, backend_result


def test_session_lazy_starts_and_maps_python_results() -> None:
    protocol = PythonExecutionResponse(
        success=True, stdout="hi\n", value_repr="42"
    ).model_dump_json()
    backend = FakeBackend(
        queue=[backend_result(stdout=protocol, command=("python", "-u", "-c", "runner"))]
    )
    session = SandboxSession(ModalSandboxConfig(), backend=backend)

    result = session.run_python("print('hi')\n40 + 2")

    assert backend.is_started is True
    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.success is True
    assert result.stdout == "hi\n"
    assert result.value_repr == "42"


def test_shell_non_zero_exit_is_normal_result_not_exception() -> None:
    backend = FakeBackend(
        queue=[backend_result(stderr="boom\n", exit_code=2, command=("/bin/bash", "-lc", "false"))]
    )
    session = SandboxSession(ModalSandboxConfig(), backend=backend)

    result = session.run_shell("false")

    assert result.status is ExecutionStatus.FAILED
    assert result.success is False
    assert result.error_type == "NonZeroExit"
    assert result.exit_code == 2


def test_python_timeout_sentinel_maps_to_timed_out_result() -> None:
    backend = FakeBackend(
        queue=[
            backend_result(
                exit_code=-1,
                error_type="ExecTimeoutError",
                error_message="Command exceeded timeout of 1 seconds.",
                command=("python", "-u", "-c", "runner"),
            )
        ]
    )
    session = SandboxSession(ModalSandboxConfig(), backend=backend)

    result = session.run_python("import time\ntime.sleep(5)", timeout_seconds=1)

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.success is False
    assert result.error_type == "ExecTimeoutError"


def test_python_timeout_error_type_maps_to_timed_out_result_even_with_signal_exit() -> None:
    backend = FakeBackend(
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
    session = SandboxSession(ModalSandboxConfig(), backend=backend)

    result = session.run_python("import time\ntime.sleep(5)", timeout_seconds=1)

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.success is False
    assert result.error_type == "ExecTimeoutError"
    assert "timeout of 1 seconds" in (result.error_message or "")
    assert result.exit_code is None


def test_python_timeout_like_missing_payload_maps_to_timed_out_result() -> None:
    started_at = datetime.now(UTC)
    backend = FakeBackend(
        queue=[
            replace(
                backend_result(
                    stdout="",
                    stderr="",
                    exit_code=137,
                    command=("python", "-u", "-c", "runner"),
                ),
                started_at=started_at,
                completed_at=started_at + timedelta(seconds=1.05),
            )
        ]
    )
    session = SandboxSession(ModalSandboxConfig(), backend=backend)

    result = session.run_python("import time\ntime.sleep(5)", timeout_seconds=1)

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.success is False
    assert result.error_type == "ExecTimeoutError"
    assert "without a JSON payload" in (result.error_message or "")
    assert result.exit_code is None


def test_python_missing_payload_with_no_exit_code_maps_to_timed_out_result() -> None:
    started_at = datetime.now(UTC)
    backend = FakeBackend(
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
    session = SandboxSession(ModalSandboxConfig(), backend=backend)

    result = session.run_python("import time\ntime.sleep(5)", timeout_seconds=1)

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.success is False
    assert result.error_type == "ExecTimeoutError"
    assert "without a JSON payload" in (result.error_message or "")
    assert result.exit_code is None


def test_python_missing_payload_without_timeout_hint_still_raises_protocol_error() -> None:
    started_at = datetime.now(UTC)
    backend = FakeBackend(
        queue=[
            replace(
                backend_result(
                    stdout="",
                    stderr="",
                    exit_code=1,
                    command=("python", "-u", "-c", "runner"),
                ),
                started_at=started_at,
                completed_at=started_at + timedelta(milliseconds=100),
            )
        ]
    )
    session = SandboxSession(ModalSandboxConfig(), backend=backend)

    with pytest.raises(ProtocolError, match="did not return a JSON payload"):
        session.run_python("raise SystemExit(1)", timeout_seconds=1)
