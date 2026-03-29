"""Modal-backed implementation of the sandbox backend contracts.

This module is the only place that knows about Modal SDK details such as
hydration, sandbox attach/detach, filesystem copy operations, and the timeout
sentinels returned by ``Sandbox.exec``.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import ModalSandboxConfig, NetworkMode
from ..exceptions import ArtifactError, BackendError, SandboxStartupError
from ..logging import get_logger
from .base import BackendCommandResult

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _timed_out_command_result(
    *,
    command: tuple[str, ...],
    stdout: str,
    stderr: str,
    started_at: datetime,
    sandbox_id: str | None,
    timeout_seconds: int | None,
    observed_exit_code: int | None = None,
) -> BackendCommandResult:
    """Normalize Modal timeout sentinels into the shared backend result shape."""

    timeout_message = (
        f"Command exceeded timeout of {timeout_seconds} seconds."
        if timeout_seconds is not None
        else "Command exceeded its execution timeout."
    )
    if observed_exit_code not in (None, -1):
        timeout_message += (
            f" Modal returned signal exit code {observed_exit_code} at the execution deadline."
        )
    return BackendCommandResult(
        command=command,
        stdout=stdout,
        stderr=stderr,
        exit_code=None,
        timed_out=True,
        started_at=started_at,
        completed_at=_utcnow(),
        sandbox_id=sandbox_id,
        error_type="ExecTimeoutError",
        error_message=timeout_message,
    )


def _looks_like_modal_deadline_signal_exit(
    *,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    started_at: datetime,
    completed_at: datetime,
    timeout_seconds: int | None,
) -> bool:
    """Detect the observed deadline-enforcement shapes exposed by Modal.

    Live verification showed Modal can enforce a deadline by returning either a
    signal exit or no exit code at all, both with empty stdout/stderr, instead
    of raising ``ExecTimeoutError`` or returning ``-1``. Keep this heuristic
    narrow so unrelated command failures stay visible.
    """

    if timeout_seconds is None or exit_code not in {None, 137, 143}:
        return False
    if stdout.strip() or stderr.strip():
        return False
    elapsed_seconds = (completed_at - started_at).total_seconds()
    return elapsed_seconds >= float(timeout_seconds)


def _import_modal() -> Any:
    """Import the Modal SDK with a library-specific error message."""

    try:
        import modal
    except ImportError as exc:  # pragma: no cover - exercised in real installs
        raise BackendError(
            "The 'modal' package is required to use the Modal backend. "
            "Install project dependencies first."
        ) from exc
    return modal


class ModalBackend:
    """Thin adapter around Modal Sandboxes.

    The backend owns SDK-specific lifecycle behavior: creating or hydrating a
    sandbox, ensuring the working directory exists, normalizing timeout paths,
    and copying artifacts between the sandbox filesystem and the local machine.
    """

    def __init__(self, config: ModalSandboxConfig, *, sandbox_id: str | None = None) -> None:
        self._config = config
        self._sandbox_id = sandbox_id
        self._sandbox: Any | None = None

    @property
    def sandbox_id(self) -> str | None:
        return self._sandbox_id

    @property
    def is_started(self) -> bool:
        return self._sandbox is not None

    def start(self) -> str:
        """Create or re-hydrate the backing sandbox and cache the live handle."""

        if self._sandbox is not None and self._sandbox_id is not None:
            return self._sandbox_id

        modal = _import_modal()
        try:
            if self._sandbox_id is not None:
                sandbox = modal.Sandbox.from_id(self._sandbox_id)
            else:
                app = modal.App.lookup(self._config.app_name, create_if_missing=True)
                sandbox = modal.Sandbox.create(
                    app=app,
                    image=self._build_image(modal),
                    **self._sandbox_create_kwargs(),
                )
            sandbox.hydrate()
            self._sandbox = sandbox
            self._sandbox_id = str(sandbox.object_id)
            if self._config.tags:
                sandbox.set_tags(self._config.tags)
            self._ensure_workspace()
            logger.debug(
                "Modal sandbox ready",
                extra={
                    "session_app": self._config.app_name,
                    "sandbox_id": self._sandbox_id,
                    "working_dir": self._config.working_dir,
                },
            )
            return self._sandbox_id
        except modal.Error as exc:
            raise SandboxStartupError(f"Unable to start Modal sandbox: {exc}") from exc

    async def astart(self) -> str:
        """Async variant of :meth:`start`."""

        if self._sandbox is not None and self._sandbox_id is not None:
            return self._sandbox_id

        modal = _import_modal()
        try:
            if self._sandbox_id is not None:
                sandbox = await modal.Sandbox.from_id.aio(self._sandbox_id)
            else:
                app = await modal.App.lookup.aio(self._config.app_name, create_if_missing=True)
                sandbox = await modal.Sandbox.create.aio(
                    app=app,
                    image=self._build_image(modal),
                    **self._sandbox_create_kwargs(),
                )
            await sandbox.hydrate.aio()
            self._sandbox = sandbox
            self._sandbox_id = str(sandbox.object_id)
            if self._config.tags:
                await sandbox.set_tags.aio(self._config.tags)
            await self._aensure_workspace()
            logger.debug(
                "Modal sandbox ready",
                extra={
                    "session_app": self._config.app_name,
                    "sandbox_id": self._sandbox_id,
                    "working_dir": self._config.working_dir,
                },
            )
            return self._sandbox_id
        except modal.Error as exc:
            raise SandboxStartupError(f"Unable to start Modal sandbox: {exc}") from exc

    def run(
        self,
        command: Sequence[str],
        *,
        stdin_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> BackendCommandResult:
        """Start the sandbox if needed, then execute one command."""

        self.start()
        return self._execute(command, stdin_text=stdin_text, timeout_seconds=timeout_seconds)

    async def arun(
        self,
        command: Sequence[str],
        *,
        stdin_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> BackendCommandResult:
        """Async variant of :meth:`run`."""

        await self.astart()
        return await self._aexecute(command, stdin_text=stdin_text, timeout_seconds=timeout_seconds)

    def read_text(self, remote_path: str) -> str:
        """Read a text file from the sandbox filesystem."""

        sandbox = self._require_sandbox()
        modal = _import_modal()
        try:
            return sandbox.filesystem.read_text(remote_path)
        except modal.Error as exc:
            raise ArtifactError(f"Failed to read sandbox file {remote_path!r}: {exc}") from exc

    async def aread_text(self, remote_path: str) -> str:
        """Async variant of :meth:`read_text`."""

        sandbox = self._require_sandbox()
        modal = _import_modal()
        try:
            return await sandbox.filesystem.read_text.aio(remote_path)
        except modal.Error as exc:
            raise ArtifactError(f"Failed to read sandbox file {remote_path!r}: {exc}") from exc

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Copy a sandbox file to a local destination, creating parent dirs first."""

        sandbox = self._require_sandbox()
        modal = _import_modal()
        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            sandbox.filesystem.copy_to_local(remote_path, str(destination))
        except modal.Error as exc:
            raise ArtifactError(
                f"Failed to download sandbox file {remote_path!r} to {str(destination)!r}: {exc}"
            ) from exc

    async def adownload_file(self, remote_path: str, local_path: str) -> None:
        """Async variant of :meth:`download_file`."""

        sandbox = self._require_sandbox()
        modal = _import_modal()
        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            await sandbox.filesystem.copy_to_local.aio(remote_path, str(destination))
        except modal.Error as exc:
            raise ArtifactError(
                f"Failed to download sandbox file {remote_path!r} to {str(destination)!r}: {exc}"
            ) from exc

    def terminate(self) -> None:
        """Terminate the sandbox if a live attachment exists."""

        if self._sandbox is None:
            return
        modal = _import_modal()
        try:
            self._sandbox.terminate()
        except modal.Error as exc:
            raise BackendError(f"Failed to terminate Modal sandbox: {exc}") from exc

    async def aterminate(self) -> None:
        """Async variant of :meth:`terminate`."""

        if self._sandbox is None:
            return
        modal = _import_modal()
        try:
            await self._sandbox.terminate.aio()
        except modal.Error as exc:
            raise BackendError(f"Failed to terminate Modal sandbox: {exc}") from exc

    def detach(self) -> None:
        """Drop the local attachment while leaving the remote sandbox alive."""

        if self._sandbox is None:
            return
        modal = _import_modal()
        try:
            self._sandbox.detach()
        except modal.Error as exc:
            raise BackendError(f"Failed to detach from Modal sandbox: {exc}") from exc
        finally:
            self._sandbox = None

    async def adetach(self) -> None:
        """Async variant of :meth:`detach`."""

        if self._sandbox is None:
            return
        modal = _import_modal()
        try:
            await self._sandbox.detach.aio()
        except modal.Error as exc:
            raise BackendError(f"Failed to detach from Modal sandbox: {exc}") from exc
        finally:
            self._sandbox = None

    def _build_image(self, modal: Any) -> Any:
        """Resolve the image to use for sandbox creation.

        A caller-provided image wins. Otherwise the backend builds a minimal
        Debian image and installs any requested Python packages.
        """

        if self._config.image is not None:
            return self._config.image
        image = modal.Image.debian_slim(python_version=self._config.python_version)
        if self._config.python_packages:
            image = image.pip_install(*self._config.python_packages)
        return image

    def _network_kwargs(self) -> dict[str, Any]:
        """Translate the public network policy into Modal create arguments."""

        if self._config.network.mode is NetworkMode.BLOCKED:
            return {"block_network": True}
        if self._config.network.mode is NetworkMode.ALLOWLIST:
            return {"cidr_allowlist": list(self._config.network.cidr_allowlist)}
        return {}

    def _sandbox_create_kwargs(self) -> dict[str, Any]:
        """Collect Modal ``Sandbox.create`` keyword arguments from config."""

        kwargs: dict[str, Any] = {
            "timeout": self._config.timeout_seconds,
            "verbose": self._config.verbose,
            **self._network_kwargs(),
        }
        if self._config.idle_timeout_seconds is not None:
            kwargs["idle_timeout"] = self._config.idle_timeout_seconds
        if self._config.secrets:
            kwargs["secrets"] = list(self._config.secrets)
        if self._config.cpu is not None:
            kwargs["cpu"] = self._config.cpu
        if self._config.memory_mb is not None:
            kwargs["memory"] = self._config.memory_mb
        return kwargs

    def _require_sandbox(self) -> Any:
        """Return the hydrated sandbox handle or fail with a backend error."""

        if self._sandbox is None:
            raise BackendError("Sandbox has not been started.")
        return self._sandbox

    def _ensure_workspace(self) -> None:
        """Create the configured working directory inside the sandbox."""

        command = ("/bin/sh", "-lc", f"mkdir -p {shlex.quote(self._config.working_dir)}")
        self._execute(command, timeout_seconds=min(self._config.default_exec_timeout_seconds, 30))

    async def _aensure_workspace(self) -> None:
        """Async variant of :meth:`_ensure_workspace`."""

        command = ("/bin/sh", "-lc", f"mkdir -p {shlex.quote(self._config.working_dir)}")
        await self._aexecute(
            command, timeout_seconds=min(self._config.default_exec_timeout_seconds, 30)
        )

    def _execute(
        self,
        command: Sequence[str],
        *,
        stdin_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> BackendCommandResult:
        """Execute a command and normalize Modal timeout behavior.

        Modal can surface timeouts either by raising ``ExecTimeoutError`` or by
        returning ``exit_code == -1``. Both paths are mapped into the same
        ``BackendCommandResult`` contract.
        """

        modal = _import_modal()
        sandbox = self._require_sandbox()
        process: Any | None = None
        started_at = _utcnow()
        cmd = tuple(command)
        try:
            process = sandbox.exec(*cmd, timeout=timeout_seconds, text=True)
            if stdin_text is not None:
                process.stdin.write(stdin_text)
                process.stdin.write_eof()
                process.stdin.drain()
            exit_code = process.wait()
            stdout = process.stdout.read()
            stderr = process.stderr.read()
            completed_at = _utcnow()
            if exit_code == -1 and timeout_seconds is not None:
                return _timed_out_command_result(
                    command=cmd,
                    stdout=stdout,
                    stderr=stderr,
                    started_at=started_at,
                    sandbox_id=self._sandbox_id,
                    timeout_seconds=timeout_seconds,
                )
            if _looks_like_modal_deadline_signal_exit(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                started_at=started_at,
                completed_at=completed_at,
                timeout_seconds=timeout_seconds,
            ):
                logger.debug(
                    (
                        "Modal command timeout surfaced without a normal timeout "
                        "sentinel; normalizing to ExecTimeoutError"
                    ),
                    extra={
                        "sandbox_id": self._sandbox_id,
                        "command": cmd,
                        "exit_code": exit_code,
                        "timeout_seconds": timeout_seconds,
                        "elapsed_seconds": (completed_at - started_at).total_seconds(),
                    },
                )
                return _timed_out_command_result(
                    command=cmd,
                    stdout=stdout,
                    stderr=stderr,
                    started_at=started_at,
                    sandbox_id=self._sandbox_id,
                    timeout_seconds=timeout_seconds,
                    observed_exit_code=exit_code,
                )
            return BackendCommandResult(
                command=cmd,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                timed_out=False,
                started_at=started_at,
                completed_at=completed_at,
                sandbox_id=self._sandbox_id,
            )
        except modal.exception.ExecTimeoutError:
            return _timed_out_command_result(
                command=cmd,
                stdout=self._safe_read(process.stdout) if process is not None else "",
                stderr=self._safe_read(process.stderr) if process is not None else "",
                started_at=started_at,
                sandbox_id=self._sandbox_id,
                timeout_seconds=timeout_seconds,
            )
        except modal.Error as exc:
            raise BackendError(f"Modal command execution failed: {exc}") from exc

    async def _aexecute(
        self,
        command: Sequence[str],
        *,
        stdin_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> BackendCommandResult:
        """Async variant of :meth:`_execute`."""

        modal = _import_modal()
        sandbox = self._require_sandbox()
        process: Any | None = None
        started_at = _utcnow()
        cmd = tuple(command)
        try:
            process = await sandbox.exec.aio(*cmd, timeout=timeout_seconds, text=True)
            if stdin_text is not None:
                process.stdin.write(stdin_text)
                process.stdin.write_eof()
                await process.stdin.drain.aio()
            exit_code = await process.wait.aio()
            stdout = await process.stdout.read.aio()
            stderr = await process.stderr.read.aio()
            completed_at = _utcnow()
            if exit_code == -1 and timeout_seconds is not None:
                return _timed_out_command_result(
                    command=cmd,
                    stdout=stdout,
                    stderr=stderr,
                    started_at=started_at,
                    sandbox_id=self._sandbox_id,
                    timeout_seconds=timeout_seconds,
                )
            if _looks_like_modal_deadline_signal_exit(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                started_at=started_at,
                completed_at=completed_at,
                timeout_seconds=timeout_seconds,
            ):
                logger.debug(
                    (
                        "Async Modal command timeout surfaced without a normal "
                        "timeout sentinel; normalizing to ExecTimeoutError"
                    ),
                    extra={
                        "sandbox_id": self._sandbox_id,
                        "command": cmd,
                        "exit_code": exit_code,
                        "timeout_seconds": timeout_seconds,
                        "elapsed_seconds": (completed_at - started_at).total_seconds(),
                    },
                )
                return _timed_out_command_result(
                    command=cmd,
                    stdout=stdout,
                    stderr=stderr,
                    started_at=started_at,
                    sandbox_id=self._sandbox_id,
                    timeout_seconds=timeout_seconds,
                    observed_exit_code=exit_code,
                )
            return BackendCommandResult(
                command=cmd,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                timed_out=False,
                started_at=started_at,
                completed_at=completed_at,
                sandbox_id=self._sandbox_id,
            )
        except modal.exception.ExecTimeoutError:
            return _timed_out_command_result(
                command=cmd,
                stdout=await self._asafe_read(process.stdout) if process is not None else "",
                stderr=await self._asafe_read(process.stderr) if process is not None else "",
                started_at=started_at,
                sandbox_id=self._sandbox_id,
                timeout_seconds=timeout_seconds,
            )
        except modal.Error as exc:
            raise BackendError(f"Modal command execution failed: {exc}") from exc

    @staticmethod
    def _safe_read(stream: Any) -> str:
        """Best-effort stdout/stderr read used during timeout cleanup paths."""

        try:
            return stream.read()
        except Exception:
            return ""

    @staticmethod
    async def _asafe_read(stream: Any) -> str:
        """Async variant of :meth:`_safe_read`."""

        try:
            return await stream.read.aio()
        except Exception:
            return ""
