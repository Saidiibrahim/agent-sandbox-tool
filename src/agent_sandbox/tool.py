from __future__ import annotations

from .exceptions import AgentSandboxError
from .models import ExecutionKind, ExecutionResult
from .session import AsyncSandboxSession, SandboxSession


class PythonSandboxTool:
    """Thin callable wrapper for agent frameworks or custom tool registries."""

    name = "sandbox_python"
    description = (
        "Execute Python code in an isolated remote sandbox and return a structured JSON result."
    )

    def __init__(self, session: SandboxSession, *, default_timeout_seconds: int | None = None) -> None:
        self._session = session
        self._default_timeout_seconds = default_timeout_seconds

    def execute(self, code: str) -> ExecutionResult:
        return self._session.run_python(code, timeout_seconds=self._default_timeout_seconds)

    def __call__(self, code: str) -> dict[str, object]:
        try:
            return self.execute(code).as_tool_payload()
        except AgentSandboxError as exc:
            return ExecutionResult.backend_error(
                kind=ExecutionKind.PYTHON,
                session_id=self._session.session_id,
                sandbox_id=self._session.sandbox_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            ).as_tool_payload()


class ShellSandboxTool:
    name = "sandbox_shell"
    description = (
        "Execute a shell command in an isolated remote sandbox and return a structured JSON result."
    )

    def __init__(self, session: SandboxSession, *, default_timeout_seconds: int | None = None) -> None:
        self._session = session
        self._default_timeout_seconds = default_timeout_seconds

    def execute(self, command: str) -> ExecutionResult:
        return self._session.run_shell(command, timeout_seconds=self._default_timeout_seconds)

    def __call__(self, command: str) -> dict[str, object]:
        try:
            return self.execute(command).as_tool_payload()
        except AgentSandboxError as exc:
            return ExecutionResult.backend_error(
                kind=ExecutionKind.SHELL,
                session_id=self._session.session_id,
                sandbox_id=self._session.sandbox_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            ).as_tool_payload()


class AsyncPythonSandboxTool:
    name = PythonSandboxTool.name
    description = PythonSandboxTool.description

    def __init__(
        self,
        session: AsyncSandboxSession,
        *,
        default_timeout_seconds: int | None = None,
    ) -> None:
        self._session = session
        self._default_timeout_seconds = default_timeout_seconds

    async def execute(self, code: str) -> ExecutionResult:
        return await self._session.run_python(code, timeout_seconds=self._default_timeout_seconds)

    async def __call__(self, code: str) -> dict[str, object]:
        try:
            return (await self.execute(code)).as_tool_payload()
        except AgentSandboxError as exc:
            return ExecutionResult.backend_error(
                kind=ExecutionKind.PYTHON,
                session_id=self._session.session_id,
                sandbox_id=self._session.sandbox_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            ).as_tool_payload()


class AsyncShellSandboxTool:
    name = ShellSandboxTool.name
    description = ShellSandboxTool.description

    def __init__(
        self,
        session: AsyncSandboxSession,
        *,
        default_timeout_seconds: int | None = None,
    ) -> None:
        self._session = session
        self._default_timeout_seconds = default_timeout_seconds

    async def execute(self, command: str) -> ExecutionResult:
        return await self._session.run_shell(
            command,
            timeout_seconds=self._default_timeout_seconds,
        )

    async def __call__(self, command: str) -> dict[str, object]:
        try:
            return (await self.execute(command)).as_tool_payload()
        except AgentSandboxError as exc:
            return ExecutionResult.backend_error(
                kind=ExecutionKind.SHELL,
                session_id=self._session.session_id,
                sandbox_id=self._session.sandbox_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            ).as_tool_payload()
