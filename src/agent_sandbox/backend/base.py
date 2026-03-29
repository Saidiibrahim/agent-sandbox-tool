"""Backend-neutral contracts used by the session layer.

The library keeps Modal-specific behavior behind these protocols so the public
session APIs can map command results, artifact reads, and lifecycle operations
without importing the Modal SDK directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(slots=True, frozen=True)
class BackendCommandResult:
    """Normalized command record returned by a sandbox backend.

    The session layer uses this shape to detect timeout sentinels, preserve raw
    stdout/stderr, and map backend outcomes into stable ``ExecutionResult``
    objects.
    """

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
    """Synchronous backend contract consumed by ``SandboxSession``."""

    @property
    def sandbox_id(self) -> str | None: ...

    @property
    def is_started(self) -> bool: ...

    def start(self) -> str:
        """Create or hydrate the remote sandbox and return its identifier."""
        ...

    def run(
        self,
        command: Sequence[str],
        *,
        stdin_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> BackendCommandResult:
        """Execute one command inside the sandbox."""
        ...

    def read_text(self, remote_path: str) -> str:
        """Read a text artifact from the sandbox filesystem."""
        ...

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Copy one sandbox file to a local destination path."""
        ...

    def terminate(self) -> None:
        """Terminate the remote sandbox permanently."""
        ...

    def detach(self) -> None:
        """Release the local attachment without terminating the sandbox."""
        ...


class AsyncSandboxBackend(Protocol):
    """Asynchronous backend contract consumed by ``AsyncSandboxSession``."""

    @property
    def sandbox_id(self) -> str | None: ...

    @property
    def is_started(self) -> bool: ...

    async def astart(self) -> str:
        """Create or hydrate the remote sandbox and return its identifier."""
        ...

    async def arun(
        self,
        command: Sequence[str],
        *,
        stdin_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> BackendCommandResult:
        """Execute one command inside the sandbox."""
        ...

    async def aread_text(self, remote_path: str) -> str:
        """Read a text artifact from the sandbox filesystem."""
        ...

    async def adownload_file(self, remote_path: str, local_path: str) -> None:
        """Copy one sandbox file to a local destination path."""
        ...

    async def aterminate(self) -> None:
        """Terminate the remote sandbox permanently."""
        ...

    async def adetach(self) -> None:
        """Release the local attachment without terminating the sandbox."""
        ...
