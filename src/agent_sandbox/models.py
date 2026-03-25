from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionKind(str, Enum):
    PYTHON = "python"
    SHELL = "shell"


class ExecutionStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    BACKEND_ERROR = "backend_error"


class SandboxHandle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    sandbox_id: str
    app_name: str
    working_dir: str


class ExecutionResult(BaseModel):
    """Structured result returned to the embedding application."""

    model_config = ConfigDict(extra="forbid")

    kind: ExecutionKind
    status: ExecutionStatus
    success: bool
    command: tuple[str, ...] = Field(default_factory=tuple)
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    exit_code: int | None = None
    value_repr: str | None = None
    value_repr_truncated: bool = False
    error_type: str | None = None
    error_message: str | None = None
    traceback: str | None = None
    session_id: str
    sandbox_id: str | None = None
    started_at: datetime
    completed_at: datetime
    duration_seconds: float

    @classmethod
    def backend_error(
        cls,
        *,
        kind: ExecutionKind,
        session_id: str,
        sandbox_id: str | None,
        error_type: str,
        error_message: str,
        command: tuple[str, ...] = (),
        traceback: str | None = None,
    ) -> "ExecutionResult":
        now = datetime.now(timezone.utc)
        return cls(
            kind=kind,
            status=ExecutionStatus.BACKEND_ERROR,
            success=False,
            command=command,
            error_type=error_type,
            error_message=error_message,
            traceback=traceback,
            session_id=session_id,
            sandbox_id=sandbox_id,
            started_at=now,
            completed_at=now,
            duration_seconds=0.0,
        )

    def as_tool_payload(self) -> dict[str, Any]:
        """Serialize the result into plain JSON-compatible data."""

        return self.model_dump(mode="json")
