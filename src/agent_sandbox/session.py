from __future__ import annotations

import asyncio
import shlex
import threading
import uuid
from typing import TYPE_CHECKING

from .config import ModalSandboxConfig
from .exceptions import ProtocolError, SessionClosedError, SessionDetachedError
from .execution.python_runner import build_python_command, build_python_request, parse_python_response
from .models import ExecutionKind, ExecutionResult, ExecutionStatus, SandboxHandle

if TYPE_CHECKING:
    from .backend.base import AsyncSandboxBackend, BackendCommandResult, SyncSandboxBackend


class SandboxSession:
    """Synchronous public API.

    The session owns local lifecycle state. The backend owns Modal-specific behavior.
    """

    def __init__(
        self,
        config: ModalSandboxConfig,
        *,
        backend: "SyncSandboxBackend | None" = None,
        sandbox_id: str | None = None,
    ) -> None:
        self._config = config
        self._backend = backend or self._build_default_backend(config, sandbox_id=sandbox_id)
        self._session_id = uuid.uuid4().hex
        self._closed = False
        self._detached = False
        self._lock = threading.RLock()

    @staticmethod
    def _build_default_backend(
        config: ModalSandboxConfig,
        *,
        sandbox_id: str | None = None,
    ) -> "SyncSandboxBackend":
        from .backend.modal_backend import ModalBackend

        return ModalBackend(config, sandbox_id=sandbox_id)

    @classmethod
    def attach(cls, sandbox_id: str, config: ModalSandboxConfig) -> "SandboxSession":
        return cls(config, sandbox_id=sandbox_id)

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def sandbox_id(self) -> str | None:
        return self._backend.sandbox_id

    @property
    def is_started(self) -> bool:
        return self._backend.is_started

    def start(self) -> SandboxHandle:
        with self._lock:
            self._ensure_usable()
            sandbox_id = self._backend.start()
            return SandboxHandle(
                session_id=self._session_id,
                sandbox_id=sandbox_id,
                app_name=self._config.app_name,
                working_dir=self._config.working_dir,
            )

    def run_python(self, code: str, *, timeout_seconds: int | None = None) -> ExecutionResult:
        with self._lock:
            handle = self.start()
            request = build_python_request(
                code=code,
                working_dir=self._config.working_dir,
                max_output_chars=self._config.max_output_chars,
                max_value_repr_chars=self._config.max_value_repr_chars,
            )
            raw = self._backend.run(
                build_python_command(),
                stdin_text=request.model_dump_json(),
                timeout_seconds=timeout_seconds or self._config.default_exec_timeout_seconds,
            )
            return self._map_python_result(raw, handle)

    def run_shell(self, command: str, *, timeout_seconds: int | None = None) -> ExecutionResult:
        with self._lock:
            handle = self.start()
            shell_command = self._build_shell_command(command)
            raw = self._backend.run(
                shell_command,
                timeout_seconds=timeout_seconds or self._config.default_exec_timeout_seconds,
            )
            return self._map_shell_result(raw, handle)

    def detach(self) -> SandboxHandle:
        with self._lock:
            handle = self.start()
            self._backend.detach()
            self._detached = True
            return handle

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                if not self._detached:
                    self._backend.terminate()
            finally:
                if not self._detached:
                    self._backend.detach()
                self._closed = True

    def __enter__(self) -> "SandboxSession":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _ensure_usable(self) -> None:
        if self._closed:
            raise SessionClosedError("This sandbox session has already been closed.")
        if self._detached:
            raise SessionDetachedError(
                "This sandbox session has been detached. Re-attach with SandboxSession.attach(...)."
            )

    def _build_shell_command(self, command: str) -> tuple[str, str, str]:
        script = f"cd {shlex.quote(self._config.working_dir)} && {command}"
        return (self._config.shell_executable, "-lc", script)

    def _map_python_result(self, raw: "BackendCommandResult", handle: SandboxHandle) -> ExecutionResult:
        if raw.timed_out:
            return ExecutionResult(
                kind=ExecutionKind.PYTHON,
                status=ExecutionStatus.TIMED_OUT,
                success=False,
                command=raw.command,
                stdout=raw.stdout,
                stderr=raw.stderr,
                exit_code=raw.exit_code,
                error_type=raw.error_type,
                error_message=raw.error_message,
                session_id=handle.session_id,
                sandbox_id=handle.sandbox_id,
                started_at=raw.started_at,
                completed_at=raw.completed_at,
                duration_seconds=(raw.completed_at - raw.started_at).total_seconds(),
            )

        protocol = parse_python_response(raw.stdout)
        status = ExecutionStatus.SUCCEEDED
        if protocol.runner_error:
            status = ExecutionStatus.BACKEND_ERROR
        elif not protocol.success:
            status = ExecutionStatus.FAILED

        if protocol.runner_error and raw.exit_code in (0, None):
            raise ProtocolError(
                "Python runner reported a protocol failure but the process exit code "
                "did not indicate runner failure."
            )

        return ExecutionResult(
            kind=ExecutionKind.PYTHON,
            status=status,
            success=status is ExecutionStatus.SUCCEEDED,
            command=raw.command,
            stdout=protocol.stdout,
            stderr=protocol.stderr,
            stdout_truncated=protocol.stdout_truncated,
            stderr_truncated=protocol.stderr_truncated,
            exit_code=raw.exit_code,
            value_repr=protocol.value_repr,
            value_repr_truncated=protocol.value_repr_truncated,
            error_type=protocol.error_type,
            error_message=protocol.error_message,
            traceback=protocol.traceback,
            session_id=handle.session_id,
            sandbox_id=handle.sandbox_id,
            started_at=raw.started_at,
            completed_at=raw.completed_at,
            duration_seconds=(raw.completed_at - raw.started_at).total_seconds(),
        )

    def _map_shell_result(self, raw: "BackendCommandResult", handle: SandboxHandle) -> ExecutionResult:
        if raw.timed_out:
            status = ExecutionStatus.TIMED_OUT
            success = False
            error_type = raw.error_type
            error_message = raw.error_message
        elif raw.exit_code == 0:
            status = ExecutionStatus.SUCCEEDED
            success = True
            error_type = None
            error_message = None
        else:
            status = ExecutionStatus.FAILED
            success = False
            error_type = "NonZeroExit"
            error_message = f"Command exited with status {raw.exit_code}."

        return ExecutionResult(
            kind=ExecutionKind.SHELL,
            status=status,
            success=success,
            command=raw.command,
            stdout=raw.stdout,
            stderr=raw.stderr,
            exit_code=raw.exit_code,
            error_type=error_type,
            error_message=error_message,
            session_id=handle.session_id,
            sandbox_id=handle.sandbox_id,
            started_at=raw.started_at,
            completed_at=raw.completed_at,
            duration_seconds=(raw.completed_at - raw.started_at).total_seconds(),
        )


class AsyncSandboxSession:
    """Asynchronous public API."""

    def __init__(
        self,
        config: ModalSandboxConfig,
        *,
        backend: "AsyncSandboxBackend | None" = None,
        sandbox_id: str | None = None,
    ) -> None:
        self._config = config
        self._backend = backend or self._build_default_backend(config, sandbox_id=sandbox_id)
        self._session_id = uuid.uuid4().hex
        self._closed = False
        self._detached = False
        self._lock = asyncio.Lock()

    @staticmethod
    def _build_default_backend(
        config: ModalSandboxConfig,
        *,
        sandbox_id: str | None = None,
    ) -> "AsyncSandboxBackend":
        from .backend.modal_backend import ModalBackend

        return ModalBackend(config, sandbox_id=sandbox_id)

    @classmethod
    def attach(cls, sandbox_id: str, config: ModalSandboxConfig) -> "AsyncSandboxSession":
        return cls(config, sandbox_id=sandbox_id)

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def sandbox_id(self) -> str | None:
        return self._backend.sandbox_id

    @property
    def is_started(self) -> bool:
        return self._backend.is_started

    async def start(self) -> SandboxHandle:
        async with self._lock:
            return await self._start_locked()

    async def run_python(self, code: str, *, timeout_seconds: int | None = None) -> ExecutionResult:
        async with self._lock:
            handle = await self._start_locked()
            request = build_python_request(
                code=code,
                working_dir=self._config.working_dir,
                max_output_chars=self._config.max_output_chars,
                max_value_repr_chars=self._config.max_value_repr_chars,
            )
            raw = await self._backend.arun(
                build_python_command(),
                stdin_text=request.model_dump_json(),
                timeout_seconds=timeout_seconds or self._config.default_exec_timeout_seconds,
            )
            return self._map_python_result(raw, handle)

    async def run_shell(self, command: str, *, timeout_seconds: int | None = None) -> ExecutionResult:
        async with self._lock:
            handle = await self._start_locked()
            raw = await self._backend.arun(
                self._build_shell_command(command),
                timeout_seconds=timeout_seconds or self._config.default_exec_timeout_seconds,
            )
            return self._map_shell_result(raw, handle)

    async def detach(self) -> SandboxHandle:
        async with self._lock:
            handle = await self._start_locked()
            await self._backend.adetach()
            self._detached = True
            return handle

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            try:
                if not self._detached:
                    await self._backend.aterminate()
            finally:
                if not self._detached:
                    await self._backend.adetach()
                self._closed = True

    async def __aenter__(self) -> "AsyncSandboxSession":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def _start_locked(self) -> SandboxHandle:
        self._ensure_usable()
        sandbox_id = await self._backend.astart()
        return SandboxHandle(
            session_id=self._session_id,
            sandbox_id=sandbox_id,
            app_name=self._config.app_name,
            working_dir=self._config.working_dir,
        )

    def _ensure_usable(self) -> None:
        if self._closed:
            raise SessionClosedError("This sandbox session has already been closed.")
        if self._detached:
            raise SessionDetachedError(
                "This sandbox session has been detached. Re-attach with AsyncSandboxSession.attach(...)."
            )

    def _build_shell_command(self, command: str) -> tuple[str, str, str]:
        script = f"cd {shlex.quote(self._config.working_dir)} && {command}"
        return (self._config.shell_executable, "-lc", script)

    def _map_python_result(self, raw: "BackendCommandResult", handle: SandboxHandle) -> ExecutionResult:
        if raw.timed_out:
            return ExecutionResult(
                kind=ExecutionKind.PYTHON,
                status=ExecutionStatus.TIMED_OUT,
                success=False,
                command=raw.command,
                stdout=raw.stdout,
                stderr=raw.stderr,
                exit_code=raw.exit_code,
                error_type=raw.error_type,
                error_message=raw.error_message,
                session_id=handle.session_id,
                sandbox_id=handle.sandbox_id,
                started_at=raw.started_at,
                completed_at=raw.completed_at,
                duration_seconds=(raw.completed_at - raw.started_at).total_seconds(),
            )

        protocol = parse_python_response(raw.stdout)
        status = ExecutionStatus.SUCCEEDED
        if protocol.runner_error:
            status = ExecutionStatus.BACKEND_ERROR
        elif not protocol.success:
            status = ExecutionStatus.FAILED

        if protocol.runner_error and raw.exit_code in (0, None):
            raise ProtocolError(
                "Python runner reported a protocol failure but the process exit code "
                "did not indicate runner failure."
            )

        return ExecutionResult(
            kind=ExecutionKind.PYTHON,
            status=status,
            success=status is ExecutionStatus.SUCCEEDED,
            command=raw.command,
            stdout=protocol.stdout,
            stderr=protocol.stderr,
            stdout_truncated=protocol.stdout_truncated,
            stderr_truncated=protocol.stderr_truncated,
            exit_code=raw.exit_code,
            value_repr=protocol.value_repr,
            value_repr_truncated=protocol.value_repr_truncated,
            error_type=protocol.error_type,
            error_message=protocol.error_message,
            traceback=protocol.traceback,
            session_id=handle.session_id,
            sandbox_id=handle.sandbox_id,
            started_at=raw.started_at,
            completed_at=raw.completed_at,
            duration_seconds=(raw.completed_at - raw.started_at).total_seconds(),
        )

    def _map_shell_result(self, raw: "BackendCommandResult", handle: SandboxHandle) -> ExecutionResult:
        if raw.timed_out:
            status = ExecutionStatus.TIMED_OUT
            success = False
            error_type = raw.error_type
            error_message = raw.error_message
        elif raw.exit_code == 0:
            status = ExecutionStatus.SUCCEEDED
            success = True
            error_type = None
            error_message = None
        else:
            status = ExecutionStatus.FAILED
            success = False
            error_type = "NonZeroExit"
            error_message = f"Command exited with status {raw.exit_code}."

        return ExecutionResult(
            kind=ExecutionKind.SHELL,
            status=status,
            success=success,
            command=raw.command,
            stdout=raw.stdout,
            stderr=raw.stderr,
            exit_code=raw.exit_code,
            error_type=error_type,
            error_message=error_message,
            session_id=handle.session_id,
            sandbox_id=handle.sandbox_id,
            started_at=raw.started_at,
            completed_at=raw.completed_at,
            duration_seconds=(raw.completed_at - raw.started_at).total_seconds(),
        )
