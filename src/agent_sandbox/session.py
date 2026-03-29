"""Public sync and async session APIs for Modal-backed sandboxes.

Sessions own sandbox lifecycle, run sequencing, artifact manifest diffing, and
the mapping from raw backend command results into stable ``ExecutionResult``
objects that higher-level operator surfaces can persist or serialize.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import posixpath
import shlex
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

from .config import ModalSandboxConfig
from .exceptions import (
    ArtifactError,
    ArtifactNotFoundError,
    ProtocolError,
    SessionClosedError,
    SessionDetachedError,
)
from .execution.python_runner import (
    build_python_command,
    build_python_request,
    parse_python_response,
)
from .logging import get_logger
from .models import (
    ArtifactChangeType,
    ArtifactMetadata,
    ArtifactPreview,
    ExecutionKind,
    ExecutionResult,
    ExecutionStatus,
    SandboxHandle,
    SessionInfo,
    SessionStatus,
)

if TYPE_CHECKING:
    from .backend.base import AsyncSandboxBackend, BackendCommandResult, SyncSandboxBackend

logger = get_logger(__name__)

_MANIFEST_SCRIPT = """
import json
import sys
from pathlib import Path

base = Path(sys.argv[1])
items = []
if base.exists():
    for path in base.rglob("*"):
        if path.is_file():
            stat = path.stat()
            mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
            items.append(
                {
                    "path": path.relative_to(base).as_posix(),
                    "size_bytes": int(stat.st_size),
                    "mtime_ns": int(mtime_ns),
                }
            )
items.sort(key=lambda item: item["path"])
print(json.dumps(items))
""".strip()


@dataclass(frozen=True)
class _ManifestEntry:
    """Normalized file entry used for before/after artifact manifest diffing."""

    path: str
    size_bytes: int
    mtime_ns: int


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _guess_media_type(path: str) -> str | None:
    """Best-effort media type guess used for artifact preview decisions."""

    media_type, _ = mimetypes.guess_type(path)
    return media_type


def _artifact_previewable(media_type: str | None) -> bool:
    """Return whether an artifact should be exposed through text preview APIs."""

    if media_type is None:
        return True
    return media_type.startswith("text/") or media_type in {
        "application/javascript",
        "application/json",
        "application/xml",
    }


def _join_remote_path(working_dir: str, relative_path: str) -> str:
    return posixpath.normpath(posixpath.join(working_dir, relative_path))


def _normalize_relative_artifact_path(path: str) -> str:
    """Validate a relative artifact path and keep it inside ``working_dir``."""

    cleaned = path.strip()
    if not cleaned:
        raise ArtifactNotFoundError("Artifact path must not be empty.")
    normalized = posixpath.normpath(cleaned)
    if normalized in {"", ".", "/"}:
        raise ArtifactNotFoundError(
            "Artifact path must point to a file, not the working directory."
        )
    if normalized == ".." or normalized.startswith("../"):
        raise ArtifactError("Artifact paths must stay inside the configured working_dir.")
    return normalized


def _resolve_absolute_artifact_path(working_dir: str, path: str) -> tuple[str, str]:
    """Validate an absolute artifact path and convert it back to a relative path."""

    normalized_working_dir = posixpath.normpath(working_dir)
    normalized_remote_path = posixpath.normpath(path)
    if normalized_working_dir == "/":
        if normalized_remote_path == "/":
            raise ArtifactNotFoundError(
                "Artifact path must point to a file, not the working directory."
            )
        return normalized_remote_path, normalized_remote_path.lstrip("/")
    if normalized_remote_path == normalized_working_dir:
        raise ArtifactNotFoundError(
            "Artifact path must point to a file, not the working directory."
        )
    if not normalized_remote_path.startswith(normalized_working_dir + "/"):
        raise ArtifactError("Artifact paths must stay inside the configured working_dir.")
    return normalized_remote_path, normalized_remote_path[len(normalized_working_dir) + 1 :]


def _parse_manifest(stdout: str) -> dict[str, _ManifestEntry]:
    """Parse the JSON manifest emitted by the sandbox-side manifest helper."""

    payload = stdout.strip()
    if not payload:
        return {}
    items = json.loads(payload)
    manifest: dict[str, _ManifestEntry] = {}
    for item in items:
        path = str(item["path"]).strip("/")
        if not path:
            continue
        manifest[path] = _ManifestEntry(
            path=path,
            size_bytes=int(item["size_bytes"]),
            mtime_ns=int(item["mtime_ns"]),
        )
    return manifest


def _diff_artifacts(
    *,
    before: dict[str, _ManifestEntry],
    after: dict[str, _ManifestEntry],
    working_dir: str,
) -> tuple[ArtifactMetadata, ...]:
    """Compute added and modified artifacts between two manifest snapshots."""

    artifacts: list[ArtifactMetadata] = []
    for path, current in sorted(after.items()):
        previous = before.get(path)
        if previous is None:
            change_type = ArtifactChangeType.ADDED
        elif previous.size_bytes != current.size_bytes or previous.mtime_ns != current.mtime_ns:
            change_type = ArtifactChangeType.MODIFIED
        else:
            continue

        media_type = _guess_media_type(path)
        artifacts.append(
            ArtifactMetadata(
                path=path,
                remote_path=_join_remote_path(working_dir, path),
                size_bytes=current.size_bytes,
                modified_at=datetime.fromtimestamp(current.mtime_ns / 1_000_000_000, tz=UTC),
                change_type=change_type,
                media_type=media_type,
                previewable=_artifact_previewable(media_type),
            )
        )
    return tuple(artifacts)


def _backend_result_timed_out(raw: BackendCommandResult) -> bool:
    """Return whether a backend result represents a normalized timeout path."""

    return raw.timed_out or raw.error_type == "ExecTimeoutError"


def _result_duration_seconds(raw: BackendCommandResult) -> float:
    return (raw.completed_at - raw.started_at).total_seconds()


def _timed_out_python_result(
    raw: BackendCommandResult,
    handle: SandboxHandle,
    *,
    run_id: str,
    sequence_number: int,
    artifacts: tuple[ArtifactMetadata, ...],
    exit_code: int | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        run_id=run_id,
        sequence_number=sequence_number,
        kind=ExecutionKind.PYTHON,
        status=ExecutionStatus.TIMED_OUT,
        success=False,
        command=raw.command,
        stdout=raw.stdout,
        stderr=raw.stderr,
        exit_code=exit_code,
        error_type=error_type if error_type is not None else raw.error_type,
        error_message=error_message if error_message is not None else raw.error_message,
        artifacts=artifacts,
        session_id=handle.session_id,
        sandbox_id=handle.sandbox_id,
        started_at=raw.started_at,
        completed_at=raw.completed_at,
        duration_seconds=_result_duration_seconds(raw),
    )


def _raw_timeout_hint(raw: BackendCommandResult) -> bool:
    if raw.error_type and "timeout" in raw.error_type.lower():
        return True
    if raw.error_message and "timeout" in raw.error_message.lower():
        return True
    return raw.exit_code in {None, -1, 137, 143}


def _timeout_boundary_reached(raw: BackendCommandResult, timeout_seconds: int | None) -> bool:
    if timeout_seconds is None:
        return False
    tolerance_seconds = min(0.5, timeout_seconds * 0.25)
    return _result_duration_seconds(raw) >= max(timeout_seconds - tolerance_seconds, 0)


def _should_normalize_missing_python_payload_as_timeout(
    raw: BackendCommandResult, *, timeout_seconds: int | None
) -> bool:
    return (
        timeout_seconds is not None
        and not raw.stdout.strip()
        and raw.exit_code != 0
        and _timeout_boundary_reached(raw, timeout_seconds)
        and _raw_timeout_hint(raw)
    )


def _missing_payload_timeout_message(raw: BackendCommandResult, timeout_seconds: int | None) -> str:
    if raw.error_message:
        return raw.error_message
    if timeout_seconds is None:
        return (
            "Python runner exited without a JSON payload after reaching its execution "
            "timeout boundary; normalized to timed_out."
        )
    return (
        "Python runner exited without a JSON payload after reaching the "
        f"{timeout_seconds}-second timeout boundary; normalized to timed_out."
    )


def _map_python_result(
    raw: BackendCommandResult,
    handle: SandboxHandle,
    *,
    run_id: str,
    sequence_number: int,
    artifacts: tuple[ArtifactMetadata, ...],
    timeout_seconds: int | None,
) -> ExecutionResult:
    """Map a backend Python command into the public execution result contract."""

    if _backend_result_timed_out(raw):
        return _timed_out_python_result(
            raw,
            handle,
            run_id=run_id,
            sequence_number=sequence_number,
            artifacts=artifacts,
            exit_code=None,
        )

    try:
        protocol = parse_python_response(raw.stdout)
    except ProtocolError:
        if not _should_normalize_missing_python_payload_as_timeout(
            raw, timeout_seconds=timeout_seconds
        ):
            raise
        logger.warning(
            "Normalizing Python timeout without structured runner payload",
            extra={
                "session_id": handle.session_id,
                "sandbox_id": handle.sandbox_id,
                "exit_code": raw.exit_code,
                "error_type": raw.error_type,
                "timeout_seconds": timeout_seconds,
                "duration_seconds": _result_duration_seconds(raw),
            },
        )
        return _timed_out_python_result(
            raw,
            handle,
            run_id=run_id,
            sequence_number=sequence_number,
            artifacts=artifacts,
            exit_code=None,
            error_type=raw.error_type or "ExecTimeoutError",
            error_message=_missing_payload_timeout_message(raw, timeout_seconds),
        )

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
        run_id=run_id,
        sequence_number=sequence_number,
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
        artifacts=artifacts,
        session_id=handle.session_id,
        sandbox_id=handle.sandbox_id,
        started_at=raw.started_at,
        completed_at=raw.completed_at,
        duration_seconds=_result_duration_seconds(raw),
    )


def _map_shell_result(
    raw: BackendCommandResult,
    handle: SandboxHandle,
    *,
    run_id: str,
    sequence_number: int,
    artifacts: tuple[ArtifactMetadata, ...],
) -> ExecutionResult:
    """Map a backend shell command into the public execution result contract."""

    if _backend_result_timed_out(raw):
        status = ExecutionStatus.TIMED_OUT
        success = False
        error_type = raw.error_type
        error_message = raw.error_message
        exit_code = None
    elif raw.exit_code == 0:
        status = ExecutionStatus.SUCCEEDED
        success = True
        error_type = None
        error_message = None
        exit_code = raw.exit_code
    else:
        status = ExecutionStatus.FAILED
        success = False
        error_type = "NonZeroExit"
        error_message = f"Command exited with status {raw.exit_code}."
        exit_code = raw.exit_code

    return ExecutionResult(
        run_id=run_id,
        sequence_number=sequence_number,
        kind=ExecutionKind.SHELL,
        status=status,
        success=success,
        command=raw.command,
        stdout=raw.stdout,
        stderr=raw.stderr,
        exit_code=exit_code,
        error_type=error_type,
        error_message=error_message,
        artifacts=artifacts,
        session_id=handle.session_id,
        sandbox_id=handle.sandbox_id,
        started_at=raw.started_at,
        completed_at=raw.completed_at,
        duration_seconds=_result_duration_seconds(raw),
    )


class SandboxSession:
    """Synchronous public session API.

    A session lazily starts its sandbox, serializes local operations with an
    ``RLock``, records monotonically increasing run sequence numbers, and can
    either detach for later reuse or close to terminate the underlying sandbox.
    """

    def __init__(
        self,
        config: ModalSandboxConfig,
        *,
        backend: SyncSandboxBackend | None = None,
        sandbox_id: str | None = None,
        session_id: str | None = None,
        initial_run_sequence: int = 0,
        created_at: datetime | None = None,
        last_run_id: str | None = None,
    ) -> None:
        self._config = config
        self._backend = backend or self._build_default_backend(config, sandbox_id=sandbox_id)
        self._session_id = session_id or uuid.uuid4().hex
        self._status = SessionStatus.CREATED
        self._closed = False
        self._detached = False
        self._lock = threading.RLock()
        now = _utcnow()
        self._created_at = created_at or now
        self._updated_at = now
        self._run_count = initial_run_sequence
        self._last_run_id = last_run_id

    @staticmethod
    def _build_default_backend(
        config: ModalSandboxConfig,
        *,
        sandbox_id: str | None = None,
    ) -> SyncSandboxBackend:
        from .backend.modal_backend import ModalBackend

        return ModalBackend(config, sandbox_id=sandbox_id)

    @classmethod
    def attach(
        cls,
        sandbox_id: str,
        config: ModalSandboxConfig,
        *,
        session_id: str | None = None,
        initial_run_sequence: int = 0,
        created_at: datetime | None = None,
        last_run_id: str | None = None,
    ) -> SandboxSession:
        """Create a session object that re-attaches to an existing sandbox ID."""

        return cls(
            config,
            sandbox_id=sandbox_id,
            session_id=session_id,
            initial_run_sequence=initial_run_sequence,
            created_at=created_at,
            last_run_id=last_run_id,
        )

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def sandbox_id(self) -> str | None:
        return self._backend.sandbox_id

    @property
    def is_started(self) -> bool:
        return self._backend.is_started

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def status(self) -> SessionStatus:
        return self._status

    @property
    def run_count(self) -> int:
        return self._run_count

    @property
    def last_run_id(self) -> str | None:
        return self._last_run_id

    def describe(self) -> SessionInfo:
        """Return a serializable snapshot of the current session lifecycle state."""

        return SessionInfo(
            session_id=self._session_id,
            sandbox_id=self.sandbox_id,
            app_name=self._config.app_name,
            working_dir=self._config.working_dir,
            status=self._status,
            is_closed=self._closed,
            run_count=self._run_count,
            last_run_id=self._last_run_id,
            created_at=self._created_at,
            updated_at=self._updated_at,
        )

    def start(self) -> SandboxHandle:
        """Start or re-hydrate the sandbox and return its live handle."""

        with self._lock:
            self._ensure_usable()
            sandbox_id = self._backend.start()
            self._status = SessionStatus.ACTIVE
            self._updated_at = _utcnow()
            return SandboxHandle(
                session_id=self._session_id,
                sandbox_id=sandbox_id,
                app_name=self._config.app_name,
                working_dir=self._config.working_dir,
                status=self._status,
            )

    def run_python(self, code: str, *, timeout_seconds: int | None = None) -> ExecutionResult:
        """Execute Python inside the sandbox and record artifact changes.

        The session captures manifests before and after the run so callers can
        inspect files that were added or modified by the executed code.
        """

        with self._lock:
            handle = self.start()
            run_id = uuid.uuid4().hex
            sequence_number = self._next_sequence_number()
            before = self._capture_manifest_best_effort()
            effective_timeout_seconds = timeout_seconds or self._config.default_exec_timeout_seconds
            request = build_python_request(
                code=code,
                working_dir=self._config.working_dir,
                max_output_chars=self._config.max_output_chars,
                max_value_repr_chars=self._config.max_value_repr_chars,
            )
            raw = self._backend.run(
                build_python_command(),
                stdin_text=request.model_dump_json(),
                timeout_seconds=effective_timeout_seconds,
            )
            after = self._capture_manifest_best_effort()
            result = _map_python_result(
                raw,
                handle,
                run_id=run_id,
                sequence_number=sequence_number,
                artifacts=_diff_artifacts(
                    before=before, after=after, working_dir=self._config.working_dir
                ),
                timeout_seconds=effective_timeout_seconds,
            )
            self._record_run(result)
            return result

    def run_shell(self, command: str, *, timeout_seconds: int | None = None) -> ExecutionResult:
        """Execute a shell command inside the sandbox and record artifact changes."""

        with self._lock:
            handle = self.start()
            run_id = uuid.uuid4().hex
            sequence_number = self._next_sequence_number()
            before = self._capture_manifest_best_effort()
            raw = self._backend.run(
                self._build_shell_command(command),
                timeout_seconds=timeout_seconds or self._config.default_exec_timeout_seconds,
            )
            after = self._capture_manifest_best_effort()
            result = _map_shell_result(
                raw,
                handle,
                run_id=run_id,
                sequence_number=sequence_number,
                artifacts=_diff_artifacts(
                    before=before, after=after, working_dir=self._config.working_dir
                ),
            )
            self._record_run(result)
            return result

    def read_artifact_text(self, path: str, *, max_chars: int | None = None) -> ArtifactPreview:
        """Read a text preview for one artifact while enforcing path safety rules."""

        with self._lock:
            self._ensure_usable()
            if not self.is_started:
                self.start()
            remote_path, relative_path = self._resolve_artifact_path(path)
            media_type = _guess_media_type(relative_path)
            if not _artifact_previewable(media_type):
                raise ArtifactError(f"Artifact {relative_path!r} is not previewable as text.")
            content = self._backend.read_text(remote_path)
            limit = max_chars or self._config.artifact_max_preview_chars
            return ArtifactPreview(
                path=relative_path,
                remote_path=remote_path,
                media_type=media_type,
                preview=content[:limit],
                truncated=len(content) > limit,
                size_bytes=len(content.encode("utf-8")),
            )

    def download_artifact(self, path: str, destination: str | Path) -> Path:
        """Download one artifact from the sandbox to a local destination path."""

        with self._lock:
            self._ensure_usable()
            if not self.is_started:
                self.start()
            remote_path, _ = self._resolve_artifact_path(path)
            destination_path = Path(destination)
            self._backend.download_file(remote_path, str(destination_path))
            return destination_path

    def detach(self) -> SandboxHandle:
        """Detach locally while leaving the remote sandbox alive for later reuse."""

        with self._lock:
            handle = self.start()
            self._backend.detach()
            self._detached = True
            self._status = SessionStatus.DETACHED
            self._updated_at = _utcnow()
            return handle.model_copy(update={"status": self._status})

    def close(self) -> None:
        """Close the session.

        Non-detached sessions terminate the remote sandbox before dropping the
        local attachment. Detached sessions only mark the session object closed.
        """

        with self._lock:
            if self._closed:
                return
            try:
                if not self._detached and self._backend.sandbox_id is not None:
                    if not self._backend.is_started:
                        self._backend.start()
                    self._backend.terminate()
                    self._status = SessionStatus.TERMINATED
            finally:
                if not self._detached:
                    self._backend.detach()
                self._closed = True
                self._updated_at = _utcnow()

    def __enter__(self) -> SandboxSession:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc, tb)
        self.close()

    def _ensure_usable(self) -> None:
        """Reject operations on closed or detached session objects."""

        if self._closed:
            raise SessionClosedError("This sandbox session has already been closed.")
        if self._detached:
            raise SessionDetachedError(
                "This sandbox session has been detached. Re-attach with SandboxSession.attach(...)."
            )

    def _build_shell_command(self, command: str) -> tuple[str, str, str]:
        script = f"cd {shlex.quote(self._config.working_dir)} && {command}"
        return (self._config.shell_executable, "-lc", script)

    def _capture_manifest_best_effort(self) -> dict[str, _ManifestEntry]:
        """Capture the current artifact manifest without failing the main run.

        Artifact tracking is best-effort: manifest capture failures are logged
        and treated as an empty manifest so execution results still return.
        """

        if not self._config.capture_artifacts:
            return {}
        raw = self._backend.run(
            ("python", "-c", _MANIFEST_SCRIPT, self._config.working_dir),
            timeout_seconds=min(self._config.default_exec_timeout_seconds, 30),
        )
        if raw.timed_out or raw.exit_code not in (0, None):
            logger.warning(
                "Artifact manifest capture failed",
                extra={
                    "session_id": self._session_id,
                    "sandbox_id": self.sandbox_id,
                    "exit_code": raw.exit_code,
                    "timed_out": raw.timed_out,
                },
            )
            return {}
        try:
            return _parse_manifest(raw.stdout)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Artifact manifest parsing failed",
                extra={
                    "session_id": self._session_id,
                    "sandbox_id": self.sandbox_id,
                    "error": str(exc),
                },
            )
            return {}

    def _next_sequence_number(self) -> int:
        self._run_count += 1
        return self._run_count

    def _record_run(self, result: ExecutionResult) -> None:
        self._last_run_id = result.run_id
        self._updated_at = _utcnow()

    def _resolve_artifact_path(self, path: str) -> tuple[str, str]:
        """Resolve an artifact path to both remote and relative representations."""

        cleaned = path.strip()
        if cleaned.startswith("/"):
            return _resolve_absolute_artifact_path(self._config.working_dir, cleaned)
        relative_path = _normalize_relative_artifact_path(cleaned)
        return _join_remote_path(self._config.working_dir, relative_path), relative_path


class AsyncSandboxSession:
    """Asynchronous public session API.

    The async variant preserves the same lifecycle, timeout, and artifact
    semantics as ``SandboxSession`` while using an ``asyncio.Lock`` to serialize
    concurrent operations within one event loop.
    """

    def __init__(
        self,
        config: ModalSandboxConfig,
        *,
        backend: AsyncSandboxBackend | None = None,
        sandbox_id: str | None = None,
        session_id: str | None = None,
        initial_run_sequence: int = 0,
        created_at: datetime | None = None,
        last_run_id: str | None = None,
    ) -> None:
        self._config = config
        self._backend = backend or self._build_default_backend(config, sandbox_id=sandbox_id)
        self._session_id = session_id or uuid.uuid4().hex
        self._status = SessionStatus.CREATED
        self._closed = False
        self._detached = False
        self._lock = asyncio.Lock()
        now = _utcnow()
        self._created_at = created_at or now
        self._updated_at = now
        self._run_count = initial_run_sequence
        self._last_run_id = last_run_id

    @staticmethod
    def _build_default_backend(
        config: ModalSandboxConfig,
        *,
        sandbox_id: str | None = None,
    ) -> AsyncSandboxBackend:
        from .backend.modal_backend import ModalBackend

        return ModalBackend(config, sandbox_id=sandbox_id)

    @classmethod
    def attach(
        cls,
        sandbox_id: str,
        config: ModalSandboxConfig,
        *,
        session_id: str | None = None,
        initial_run_sequence: int = 0,
        created_at: datetime | None = None,
        last_run_id: str | None = None,
    ) -> AsyncSandboxSession:
        """Create a session object that re-attaches to an existing sandbox ID."""

        return cls(
            config,
            sandbox_id=sandbox_id,
            session_id=session_id,
            initial_run_sequence=initial_run_sequence,
            created_at=created_at,
            last_run_id=last_run_id,
        )

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def sandbox_id(self) -> str | None:
        return self._backend.sandbox_id

    @property
    def is_started(self) -> bool:
        return self._backend.is_started

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def status(self) -> SessionStatus:
        return self._status

    @property
    def run_count(self) -> int:
        return self._run_count

    @property
    def last_run_id(self) -> str | None:
        return self._last_run_id

    def describe(self) -> SessionInfo:
        """Return a serializable snapshot of the current session lifecycle state."""

        return SessionInfo(
            session_id=self._session_id,
            sandbox_id=self.sandbox_id,
            app_name=self._config.app_name,
            working_dir=self._config.working_dir,
            status=self._status,
            is_closed=self._closed,
            run_count=self._run_count,
            last_run_id=self._last_run_id,
            created_at=self._created_at,
            updated_at=self._updated_at,
        )

    async def start(self) -> SandboxHandle:
        """Start or re-hydrate the sandbox and return its live handle."""

        async with self._lock:
            return await self._start_locked()

    async def run_python(self, code: str, *, timeout_seconds: int | None = None) -> ExecutionResult:
        """Execute Python inside the sandbox and record artifact changes."""

        async with self._lock:
            handle = await self._start_locked()
            run_id = uuid.uuid4().hex
            sequence_number = self._next_sequence_number()
            before = await self._capture_manifest_best_effort()
            effective_timeout_seconds = timeout_seconds or self._config.default_exec_timeout_seconds
            request = build_python_request(
                code=code,
                working_dir=self._config.working_dir,
                max_output_chars=self._config.max_output_chars,
                max_value_repr_chars=self._config.max_value_repr_chars,
            )
            raw = await self._backend.arun(
                build_python_command(),
                stdin_text=request.model_dump_json(),
                timeout_seconds=effective_timeout_seconds,
            )
            after = await self._capture_manifest_best_effort()
            result = _map_python_result(
                raw,
                handle,
                run_id=run_id,
                sequence_number=sequence_number,
                artifacts=_diff_artifacts(
                    before=before, after=after, working_dir=self._config.working_dir
                ),
                timeout_seconds=effective_timeout_seconds,
            )
            self._record_run(result)
            return result

    async def run_shell(
        self, command: str, *, timeout_seconds: int | None = None
    ) -> ExecutionResult:
        """Execute a shell command inside the sandbox and record artifact changes."""

        async with self._lock:
            handle = await self._start_locked()
            run_id = uuid.uuid4().hex
            sequence_number = self._next_sequence_number()
            before = await self._capture_manifest_best_effort()
            raw = await self._backend.arun(
                self._build_shell_command(command),
                timeout_seconds=timeout_seconds or self._config.default_exec_timeout_seconds,
            )
            after = await self._capture_manifest_best_effort()
            result = _map_shell_result(
                raw,
                handle,
                run_id=run_id,
                sequence_number=sequence_number,
                artifacts=_diff_artifacts(
                    before=before, after=after, working_dir=self._config.working_dir
                ),
            )
            self._record_run(result)
            return result

    async def read_artifact_text(
        self, path: str, *, max_chars: int | None = None
    ) -> ArtifactPreview:
        """Read a text preview for one artifact while enforcing path safety rules."""

        async with self._lock:
            self._ensure_usable()
            if not self.is_started:
                await self._start_locked()
            remote_path, relative_path = self._resolve_artifact_path(path)
            media_type = _guess_media_type(relative_path)
            if not _artifact_previewable(media_type):
                raise ArtifactError(f"Artifact {relative_path!r} is not previewable as text.")
            content = await self._backend.aread_text(remote_path)
            limit = max_chars or self._config.artifact_max_preview_chars
            return ArtifactPreview(
                path=relative_path,
                remote_path=remote_path,
                media_type=media_type,
                preview=content[:limit],
                truncated=len(content) > limit,
                size_bytes=len(content.encode("utf-8")),
            )

    async def download_artifact(self, path: str, destination: str | Path) -> Path:
        """Download one artifact from the sandbox to a local destination path."""

        async with self._lock:
            self._ensure_usable()
            if not self.is_started:
                await self._start_locked()
            remote_path, _ = self._resolve_artifact_path(path)
            destination_path = Path(destination)
            await self._backend.adownload_file(remote_path, str(destination_path))
            return destination_path

    async def detach(self) -> SandboxHandle:
        """Detach locally while leaving the remote sandbox alive for later reuse."""

        async with self._lock:
            handle = await self._start_locked()
            await self._backend.adetach()
            self._detached = True
            self._status = SessionStatus.DETACHED
            self._updated_at = _utcnow()
            return handle.model_copy(update={"status": self._status})

    async def close(self) -> None:
        """Close the session and terminate the sandbox unless it was detached."""

        async with self._lock:
            if self._closed:
                return
            try:
                if not self._detached and self._backend.sandbox_id is not None:
                    if not self._backend.is_started:
                        await self._backend.astart()
                    await self._backend.aterminate()
                    self._status = SessionStatus.TERMINATED
            finally:
                if not self._detached:
                    await self._backend.adetach()
                self._closed = True
                self._updated_at = _utcnow()

    async def __aenter__(self) -> AsyncSandboxSession:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc, tb)
        await self.close()

    async def _start_locked(self) -> SandboxHandle:
        """Start the sandbox while the session lock is already held."""

        self._ensure_usable()
        sandbox_id = await self._backend.astart()
        self._status = SessionStatus.ACTIVE
        self._updated_at = _utcnow()
        return SandboxHandle(
            session_id=self._session_id,
            sandbox_id=sandbox_id,
            app_name=self._config.app_name,
            working_dir=self._config.working_dir,
            status=self._status,
        )

    def _ensure_usable(self) -> None:
        """Reject operations on closed or detached session objects."""

        if self._closed:
            raise SessionClosedError("This sandbox session has already been closed.")
        if self._detached:
            raise SessionDetachedError(
                "This sandbox session has been detached. "
                "Re-attach with AsyncSandboxSession.attach(...)."
            )

    def _build_shell_command(self, command: str) -> tuple[str, str, str]:
        script = f"cd {shlex.quote(self._config.working_dir)} && {command}"
        return (self._config.shell_executable, "-lc", script)

    async def _capture_manifest_best_effort(self) -> dict[str, _ManifestEntry]:
        """Async variant of best-effort artifact manifest capture."""

        if not self._config.capture_artifacts:
            return {}
        raw = await self._backend.arun(
            ("python", "-c", _MANIFEST_SCRIPT, self._config.working_dir),
            timeout_seconds=min(self._config.default_exec_timeout_seconds, 30),
        )
        if raw.timed_out or raw.exit_code not in (0, None):
            logger.warning(
                "Async artifact manifest capture failed",
                extra={
                    "session_id": self._session_id,
                    "sandbox_id": self.sandbox_id,
                    "exit_code": raw.exit_code,
                    "timed_out": raw.timed_out,
                },
            )
            return {}
        try:
            return _parse_manifest(raw.stdout)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Async artifact manifest parsing failed",
                extra={
                    "session_id": self._session_id,
                    "sandbox_id": self.sandbox_id,
                    "error": str(exc),
                },
            )
            return {}

    def _next_sequence_number(self) -> int:
        self._run_count += 1
        return self._run_count

    def _record_run(self, result: ExecutionResult) -> None:
        self._last_run_id = result.run_id
        self._updated_at = _utcnow()

    def _resolve_artifact_path(self, path: str) -> tuple[str, str]:
        """Resolve an artifact path to both remote and relative representations."""

        cleaned = path.strip()
        if cleaned.startswith("/"):
            return _resolve_absolute_artifact_path(self._config.working_dir, cleaned)
        relative_path = _normalize_relative_artifact_path(cleaned)
        return _join_remote_path(self._config.working_dir, relative_path), relative_path
