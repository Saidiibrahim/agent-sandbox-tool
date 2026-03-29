"""Agent-friendly tool wrappers around the session APIs.

These adapters keep the rich ``ExecutionResult`` type for direct callers while
returning plain JSON payloads for agent frameworks and tool registries that
expect serializable outputs.
"""

from __future__ import annotations

from .exceptions import AgentSandboxError
from .models import ExecutionKind, ExecutionResult
from .session import AsyncSandboxSession, SandboxSession


class PythonSandboxTool:
    """Tool wrapper that runs Python and returns JSON-serializable results."""

    name = "sandbox_python"
    description = (
        "Execute Python code in an isolated remote sandbox and return a structured JSON result."
    )

    def __init__(
        self, session: SandboxSession, *, default_timeout_seconds: int | None = None
    ) -> None:
        self._session = session
        self._default_timeout_seconds = default_timeout_seconds

    def execute(self, code: str) -> ExecutionResult:
        """Execute Python and keep the typed ``ExecutionResult`` for direct callers."""

        return self._session.run_python(code, timeout_seconds=self._default_timeout_seconds)

    def __call__(self, code: str) -> dict[str, object]:
        """Execute Python and convert domain errors into backend-style payloads."""

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
    """Tool wrapper that runs shell commands and returns JSON-serializable results."""

    name = "sandbox_shell"
    description = (
        "Execute a shell command in an isolated remote sandbox and return a structured JSON result."
    )

    def __init__(
        self, session: SandboxSession, *, default_timeout_seconds: int | None = None
    ) -> None:
        self._session = session
        self._default_timeout_seconds = default_timeout_seconds

    def execute(self, command: str) -> ExecutionResult:
        """Execute a shell command and keep the typed ``ExecutionResult``."""

        return self._session.run_shell(command, timeout_seconds=self._default_timeout_seconds)

    def __call__(self, command: str) -> dict[str, object]:
        """Execute a shell command and convert domain errors into JSON payloads."""

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
    """Async Python tool wrapper for agent runtimes that await tool calls."""

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
        """Execute Python and keep the typed async ``ExecutionResult``."""

        return await self._session.run_python(code, timeout_seconds=self._default_timeout_seconds)

    async def __call__(self, code: str) -> dict[str, object]:
        """Execute Python and convert domain errors into backend-style payloads."""

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
    """Async shell tool wrapper for agent runtimes that await tool calls."""

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
        """Execute a shell command and keep the typed async ``ExecutionResult``."""

        return await self._session.run_shell(
            command,
            timeout_seconds=self._default_timeout_seconds,
        )

    async def __call__(self, command: str) -> dict[str, object]:
        """Execute a shell command and convert domain errors into JSON payloads."""

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
