from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from agent_sandbox.backend.base import BackendCommandResult


@dataclass
class FakeBackend:
    sandbox_id_value: str = "sb-fake"
    started: bool = False
    commands: list[tuple[str, ...]] = field(default_factory=list)
    queue: list[BackendCommandResult] = field(default_factory=list)

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
        self.commands.append(tuple(command))
        return self.queue.pop(0)

    def terminate(self) -> None:
        return None

    def detach(self) -> None:
        self.started = False


@dataclass
class FakeAsyncBackend:
    sandbox_id_value: str = "sb-fake"
    started: bool = False
    commands: list[tuple[str, ...]] = field(default_factory=list)
    queue: list[BackendCommandResult] = field(default_factory=list)

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
        self.commands.append(tuple(command))
        return self.queue.pop(0)

    async def aterminate(self) -> None:
        return None

    async def adetach(self) -> None:
        self.started = False


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
    now = datetime.now(timezone.utc)
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
