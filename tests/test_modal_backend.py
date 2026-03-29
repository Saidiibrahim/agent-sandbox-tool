"""Modal backend unit tests for timeout normalization edge cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from agent_sandbox.backend.modal_backend import ModalBackend, _looks_like_modal_deadline_signal_exit
from agent_sandbox.config import ModalSandboxConfig


class _FakeModalError(Exception):
    pass


class _FakeExecTimeoutError(_FakeModalError):
    pass


class _FakeStream:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text


class _FakeStdin:
    def write(self, text: str) -> None:
        _ = text

    def write_eof(self) -> None:
        return None

    def drain(self) -> None:
        return None


@dataclass
class _FakeProcess:
    exit_code: int
    stdout_text: str = ""
    stderr_text: str = ""

    def __post_init__(self) -> None:
        self.stdin = _FakeStdin()
        self.stdout = _FakeStream(self.stdout_text)
        self.stderr = _FakeStream(self.stderr_text)

    def wait(self) -> int:
        return self.exit_code


class _FakeSandbox:
    def __init__(self, process: _FakeProcess) -> None:
        self._process = process

    def exec(self, *command: str, timeout: int | None, text: bool) -> _FakeProcess:
        _ = (command, timeout, text)
        return self._process


def _fake_modal_namespace() -> SimpleNamespace:
    return SimpleNamespace(
        Error=_FakeModalError,
        exception=SimpleNamespace(ExecTimeoutError=_FakeExecTimeoutError),
    )


def test_signal_exit_137_at_deadline_is_treated_as_timeout_shape() -> None:
    started_at = datetime.now(UTC)
    completed_at = started_at + timedelta(seconds=1.02)

    assert _looks_like_modal_deadline_signal_exit(
        exit_code=137,
        stdout="",
        stderr="",
        started_at=started_at,
        completed_at=completed_at,
        timeout_seconds=1,
    )


def test_signal_exit_before_deadline_is_not_treated_as_timeout_shape() -> None:
    started_at = datetime.now(UTC)
    completed_at = started_at + timedelta(seconds=0.4)

    assert not _looks_like_modal_deadline_signal_exit(
        exit_code=137,
        stdout="",
        stderr="",
        started_at=started_at,
        completed_at=completed_at,
        timeout_seconds=1,
    )


def test_missing_exit_code_at_deadline_is_treated_as_timeout_shape() -> None:
    started_at = datetime.now(UTC)
    completed_at = started_at + timedelta(seconds=1.02)

    assert _looks_like_modal_deadline_signal_exit(
        exit_code=None,
        stdout="",
        stderr="",
        started_at=started_at,
        completed_at=completed_at,
        timeout_seconds=1,
    )


def test_execute_normalizes_signal_exit_timeout_result(monkeypatch) -> None:
    started_at = datetime(2026, 3, 29, 6, 20, tzinfo=UTC)
    completed_at = started_at + timedelta(seconds=1.35)
    times = iter((started_at, completed_at, completed_at))
    backend = ModalBackend(ModalSandboxConfig())
    backend._sandbox = _FakeSandbox(_FakeProcess(exit_code=137))
    backend._sandbox_id = "sb-timeout"

    monkeypatch.setattr("agent_sandbox.backend.modal_backend._import_modal", _fake_modal_namespace)
    monkeypatch.setattr("agent_sandbox.backend.modal_backend._utcnow", lambda: next(times))

    result = backend._execute(("python", "-u", "-c", "runner"), timeout_seconds=1)

    assert result.timed_out is True
    assert result.exit_code is None
    assert result.error_type == "ExecTimeoutError"
    assert "signal exit code 137" in (result.error_message or "")


def test_execute_normalizes_missing_exit_code_timeout_result(monkeypatch) -> None:
    started_at = datetime(2026, 3, 29, 6, 20, tzinfo=UTC)
    completed_at = started_at + timedelta(seconds=1.35)
    times = iter((started_at, completed_at, completed_at))
    backend = ModalBackend(ModalSandboxConfig())
    backend._sandbox = _FakeSandbox(_FakeProcess(exit_code=None))
    backend._sandbox_id = "sb-timeout"

    monkeypatch.setattr("agent_sandbox.backend.modal_backend._import_modal", _fake_modal_namespace)
    monkeypatch.setattr("agent_sandbox.backend.modal_backend._utcnow", lambda: next(times))

    result = backend._execute(("python", "-u", "-c", "runner"), timeout_seconds=1)

    assert result.timed_out is True
    assert result.exit_code is None
    assert result.error_type == "ExecTimeoutError"
    assert result.error_message == "Command exceeded timeout of 1 seconds."
