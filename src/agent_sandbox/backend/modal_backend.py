from __future__ import annotations

import shlex
from datetime import datetime, timezone
from typing import Any, Sequence

from ..config import ModalSandboxConfig, NetworkMode
from ..exceptions import BackendError, SandboxStartupError
from .base import BackendCommandResult


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _import_modal() -> Any:
    try:
        import modal  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised in real installs
        raise BackendError(
            "The 'modal' package is required to use the Modal backend. "
            "Install project dependencies first."
        ) from exc
    return modal


class ModalBackend:
    """Thin adapter around Modal Sandboxes.

    The backend owns the Modal-specific concerns: App lookup, Sandbox.create / from_id,
    command execution, and resource cleanup.
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
            return self._sandbox_id
        except modal.Error as exc:
            raise SandboxStartupError(f"Unable to start Modal sandbox: {exc}") from exc

    async def astart(self) -> str:
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
        self.start()
        return self._execute(command, stdin_text=stdin_text, timeout_seconds=timeout_seconds)

    async def arun(
        self,
        command: Sequence[str],
        *,
        stdin_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> BackendCommandResult:
        await self.astart()
        return await self._aexecute(command, stdin_text=stdin_text, timeout_seconds=timeout_seconds)

    def terminate(self) -> None:
        if self._sandbox is None:
            return
        modal = _import_modal()
        try:
            self._sandbox.terminate()
        except modal.Error as exc:
            raise BackendError(f"Failed to terminate Modal sandbox: {exc}") from exc

    async def aterminate(self) -> None:
        if self._sandbox is None:
            return
        modal = _import_modal()
        try:
            await self._sandbox.terminate.aio()
        except modal.Error as exc:
            raise BackendError(f"Failed to terminate Modal sandbox: {exc}") from exc

    def detach(self) -> None:
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
        if self._config.image is not None:
            return self._config.image
        image = modal.Image.debian_slim(python_version=self._config.python_version)
        if self._config.python_packages:
            image = image.pip_install(*self._config.python_packages)
        return image

    def _network_kwargs(self) -> dict[str, Any]:
        if self._config.network.mode is NetworkMode.BLOCKED:
            return {"block_network": True}
        if self._config.network.mode is NetworkMode.ALLOWLIST:
            return {"cidr_allowlist": list(self._config.network.cidr_allowlist)}
        return {}

    def _sandbox_create_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "timeout": self._config.timeout_seconds,
            "verbose": self._config.verbose,
            **self._network_kwargs(),
        }
        if self._config.idle_timeout_seconds is not None:
            kwargs["idle_timeout"] = self._config.idle_timeout_seconds
        if self._config.secrets:
            kwargs["secrets"] = list(self._config.secrets)
        return kwargs

    def _require_sandbox(self) -> Any:
        if self._sandbox is None:
            raise BackendError("Sandbox has not been started.")
        return self._sandbox

    def _ensure_workspace(self) -> None:
        command = (
            "/bin/sh",
            "-lc",
            f"mkdir -p {shlex.quote(self._config.working_dir)}",
        )
        self._execute(command, timeout_seconds=min(self._config.default_exec_timeout_seconds, 30))

    async def _aensure_workspace(self) -> None:
        command = (
            "/bin/sh",
            "-lc",
            f"mkdir -p {shlex.quote(self._config.working_dir)}",
        )
        await self._aexecute(command, timeout_seconds=min(self._config.default_exec_timeout_seconds, 30))

    def _execute(
        self,
        command: Sequence[str],
        *,
        stdin_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> BackendCommandResult:
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
            return BackendCommandResult(
                command=cmd,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                timed_out=False,
                started_at=started_at,
                completed_at=_utcnow(),
                sandbox_id=self._sandbox_id,
            )
        except modal.exception.ExecTimeoutError as exc:
            return BackendCommandResult(
                command=cmd,
                stdout=self._safe_read(process.stdout) if process is not None else "",
                stderr=self._safe_read(process.stderr) if process is not None else "",
                exit_code=None,
                timed_out=True,
                started_at=started_at,
                completed_at=_utcnow(),
                sandbox_id=self._sandbox_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
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
            return BackendCommandResult(
                command=cmd,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                timed_out=False,
                started_at=started_at,
                completed_at=_utcnow(),
                sandbox_id=self._sandbox_id,
            )
        except modal.exception.ExecTimeoutError as exc:
            return BackendCommandResult(
                command=cmd,
                stdout=await self._asafe_read(process.stdout) if process is not None else "",
                stderr=await self._asafe_read(process.stderr) if process is not None else "",
                exit_code=None,
                timed_out=True,
                started_at=started_at,
                completed_at=_utcnow(),
                sandbox_id=self._sandbox_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        except modal.Error as exc:
            raise BackendError(f"Modal command execution failed: {exc}") from exc

    @staticmethod
    def _safe_read(stream: Any) -> str:
        try:
            return stream.read()
        except Exception:
            return ""

    @staticmethod
    async def _asafe_read(stream: Any) -> str:
        try:
            return await stream.read.aio()
        except Exception:
            return ""
