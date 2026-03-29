"""Deterministic fake backends shared by unit tests.

These fakes emulate the backend protocol closely enough to exercise session and
tool semantics without depending on a live Modal environment.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agent_sandbox.backend.base import BackendCommandResult


@dataclass
class FakeBackend:
    """Synchronous fake backend with queued command results and in-memory files."""

    sandbox_id_value: str = "sb-fake"
    started: bool = False
    commands: list[tuple[str, ...]] = field(default_factory=list)
    queue: list[BackendCommandResult] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)

    @property
    def sandbox_id(self) -> str | None:
        return self.sandbox_id_value if self.started else None

    @property
    def is_started(self) -> bool:
        return self.started

    def start(self) -> str:
        self.started = True
        return self.sandbox_id_value

    def run(
        self,
        command: Sequence[str],
        *,
        stdin_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> BackendCommandResult:
        _ = (stdin_text, timeout_seconds)
        self.started = True
        cmd = tuple(command)
        self.commands.append(cmd)
        if self._is_manifest_command(cmd):
            return backend_result(stdout="[]", command=cmd)
        return self.queue.pop(0)

    def read_text(self, remote_path: str) -> str:
        return self.files[remote_path]

    def download_file(self, remote_path: str, local_path: str) -> None:
        Path(local_path).write_text(self.files[remote_path], encoding="utf-8")

    def terminate(self) -> None:
        return None

    def detach(self) -> None:
        self.started = False

    @staticmethod
    def _is_manifest_command(command: tuple[str, ...]) -> bool:
        """Detect the helper command used for artifact manifest capture."""

        return (
            len(command) >= 4
            and command[0] == "python"
            and command[1] == "-c"
            and "items.sort" in command[2]
        )


@dataclass
class FakeAsyncBackend:
    """Async fake backend with queued command results and in-memory files."""

    sandbox_id_value: str = "sb-fake"
    started: bool = False
    commands: list[tuple[str, ...]] = field(default_factory=list)
    queue: list[BackendCommandResult] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)

    @property
    def sandbox_id(self) -> str | None:
        return self.sandbox_id_value if self.started else None

    @property
    def is_started(self) -> bool:
        return self.started

    async def astart(self) -> str:
        self.started = True
        return self.sandbox_id_value

    async def arun(
        self,
        command: Sequence[str],
        *,
        stdin_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> BackendCommandResult:
        _ = (stdin_text, timeout_seconds)
        self.started = True
        cmd = tuple(command)
        self.commands.append(cmd)
        if self._is_manifest_command(cmd):
            return backend_result(stdout="[]", command=cmd)
        return self.queue.pop(0)

    async def aread_text(self, remote_path: str) -> str:
        return self.files[remote_path]

    async def adownload_file(self, remote_path: str, local_path: str) -> None:
        Path(local_path).write_text(self.files[remote_path], encoding="utf-8")

    async def aterminate(self) -> None:
        return None

    async def adetach(self) -> None:
        self.started = False

    @staticmethod
    def _is_manifest_command(command: tuple[str, ...]) -> bool:
        """Detect the helper command used for artifact manifest capture."""

        return (
            len(command) >= 4
            and command[0] == "python"
            and command[1] == "-c"
            and "items.sort" in command[2]
        )


def backend_result(
    *,
    stdout: str = "",
    stderr: str = "",
    exit_code: int | None = 0,
    timed_out: bool = False,
    command: Sequence[str] = (),
    sandbox_id: str | None = "sb-fake",
    error_type: str | None = None,
    error_message: str | None = None,
) -> BackendCommandResult:
    """Build a timestamped backend result for fake backend queues."""

    now = datetime.now(UTC)
    return BackendCommandResult(
        command=tuple(command),
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        timed_out=timed_out,
        started_at=now,
        completed_at=now,
        sandbox_id=sandbox_id,
        error_type=error_type,
        error_message=error_message,
    )
