from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence


@dataclass(slots=True, frozen=True)
class BackendCommandResult:
    command: tuple[str, ...]
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool
    started_at: datetime
    completed_at: datetime
    sandbox_id: str | None
    error_type: str | None = None
    error_message: str | None = None


class SyncSandboxBackend(Protocol):
    @property
    def sandbox_id(self) -> str | None: ...

    @property
    def is_started(self) -> bool: ...

    def start(self) -> str: ...

    def run(
        self,
        command: Sequence[str],
        *,
        stdin_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> BackendCommandResult: ...

    def terminate(self) -> None: ...

    def detach(self) -> None: ...


class AsyncSandboxBackend(Protocol):
    @property
    def sandbox_id(self) -> str | None: ...

    @property
    def is_started(self) -> bool: ...

    async def astart(self) -> str: ...

    async def arun(
        self,
        command: Sequence[str],
        *,
        stdin_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> BackendCommandResult: ...

    async def aterminate(self) -> None: ...

    async def adetach(self) -> None: ...
