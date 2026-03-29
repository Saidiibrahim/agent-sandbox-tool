"""Shared typed models exchanged across the package.

These models capture stable lifecycle, execution, and artifact semantics so the
public sessions, CLI, state store, and HTTP service can share one contract.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionKind(StrEnum):
    """High-level execution surface exposed by the package."""

    PYTHON = "python"
    SHELL = "shell"


class ExecutionStatus(StrEnum):
    """Normalized execution outcomes presented to callers."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    BACKEND_ERROR = "backend_error"


class SessionStatus(StrEnum):
    """Lifecycle states tracked for live and persisted sessions."""

    CREATED = "created"
    ACTIVE = "active"
    DETACHED = "detached"
    TERMINATED = "terminated"


class ArtifactChangeType(StrEnum):
    """Kinds of filesystem changes surfaced after a run."""

    ADDED = "added"
    MODIFIED = "modified"


class SandboxHandle(BaseModel):
    """Live sandbox identity returned when a session is started or detached."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    sandbox_id: str
    app_name: str
    working_dir: str
    status: SessionStatus = SessionStatus.ACTIVE


class ArtifactMetadata(BaseModel):
    """Metadata for one artifact detected by manifest diffing after a run."""

    model_config = ConfigDict(extra="forbid")

    path: str
    remote_path: str
    size_bytes: int = Field(ge=0)
    modified_at: datetime
    change_type: ArtifactChangeType
    media_type: str | None = None
    previewable: bool = True


class ArtifactPreview(BaseModel):
    """Text preview returned when an artifact is read through the API surface."""

    model_config = ConfigDict(extra="forbid")

    path: str
    remote_path: str
    media_type: str | None = None
    preview: str
    truncated: bool = False
    size_bytes: int | None = Field(default=None, ge=0)


class SessionInfo(BaseModel):
    """Serializable snapshot of a session's lifecycle and run counters."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    sandbox_id: str | None = None
    app_name: str
    working_dir: str
    status: SessionStatus
    is_closed: bool = False
    run_count: int = Field(default=0, ge=0)
    last_run_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ExecutionResult(BaseModel):
    """Structured result returned to embedding applications and operator surfaces.

    Results preserve the backend command, normalized status, captured output,
    artifact diff, and timing metadata so callers can inspect failures without
    special-casing Python, shell, CLI, or HTTP response shapes.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    sequence_number: int = Field(default=0, ge=0)
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
    artifacts: tuple[ArtifactMetadata, ...] = Field(default_factory=tuple)
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
    ) -> ExecutionResult:
        """Construct a synthetic result for tool/CLI paths that fail before a run starts."""

        now = datetime.now(UTC)
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
