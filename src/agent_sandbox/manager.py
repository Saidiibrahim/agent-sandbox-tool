"""Process-friendly orchestration layer over detached sandbox sessions.

The manager re-attaches stored sessions on demand, serializes per-session work
with file locks, persists run results, and detaches again so the library can be
used safely from CLI or HTTP processes without a long-lived daemon.
"""

from __future__ import annotations

import contextlib
import fcntl
from collections.abc import Iterator
from pathlib import Path

from .config import ModalSandboxConfig
from .exceptions import ArtifactNotFoundError, SessionError
from .models import ArtifactMetadata, ArtifactPreview, ExecutionResult, SessionStatus
from .session import SandboxSession
from .state import LocalStateStore, StoredSession


class SandboxManager:
    """Process-friendly manager layered on top of ``SandboxSession``.

    Each operation acquires a per-session file lock, reconstructs a runtime
    session from persisted state, performs the requested work, and writes the
    updated lifecycle snapshot back to the local store.
    """

    def __init__(self, store: LocalStateStore | None = None) -> None:
        self.store = store or LocalStateStore()

    def start_session(
        self,
        config: ModalSandboxConfig,
        *,
        session_id: str | None = None,
    ) -> StoredSession:
        """Create a new sandbox session, detach it, and persist its handle."""

        session = SandboxSession(config, session_id=session_id)
        with self._session_lock(session.session_id):
            session.start()
            session.detach()
            record = StoredSession(info=session.describe(), config=config)
            self.store.save_session(record)
            return record

    def attach_session(
        self,
        sandbox_id: str,
        config: ModalSandboxConfig,
        *,
        session_id: str | None = None,
        initial_run_sequence: int = 0,
    ) -> StoredSession:
        """Register an existing sandbox ID for future managed reuse."""

        session = SandboxSession.attach(
            sandbox_id,
            config,
            session_id=session_id,
            initial_run_sequence=initial_run_sequence,
        )
        with self._session_lock(session.session_id):
            session.start()
            session.detach()
            record = StoredSession(info=session.describe(), config=config)
            self.store.save_session(record)
            return record

    def get_session(self, session_id: str) -> StoredSession:
        """Load one persisted session record."""

        return self.store.get_session(session_id)

    def list_sessions(self) -> list[StoredSession]:
        """List persisted sessions ordered by most recent update."""

        return self.store.list_sessions()

    def list_runs(self, *, session_id: str | None = None) -> list[ExecutionResult]:
        """List persisted runs, optionally filtered to one session."""

        return self.store.list_runs(session_id=session_id)

    def get_run(self, run_id: str) -> ExecutionResult:
        """Load one persisted run record."""

        return self.store.get_run(run_id)

    def run_python(
        self, session_id: str, code: str, *, timeout_seconds: int | None = None
    ) -> ExecutionResult:
        """Run Python inside a stored session and persist the resulting run record."""

        with self._session_lock(session_id):
            record = self.store.get_session(session_id)
            self._ensure_attachable(record)
            session = self._build_runtime_session(record)
            try:
                result = session.run_python(code, timeout_seconds=timeout_seconds)
                self.store.save_run(result)
            finally:
                self._finalize_session(session, record)
            return result

    def run_shell(
        self,
        session_id: str,
        command: str,
        *,
        timeout_seconds: int | None = None,
    ) -> ExecutionResult:
        """Run a shell command inside a stored session and persist the run record."""

        with self._session_lock(session_id):
            record = self.store.get_session(session_id)
            self._ensure_attachable(record)
            session = self._build_runtime_session(record)
            try:
                result = session.run_shell(command, timeout_seconds=timeout_seconds)
                self.store.save_run(result)
            finally:
                self._finalize_session(session, record)
            return result

    def terminate_session(self, session_id: str) -> StoredSession:
        """Terminate a stored session and persist the terminal lifecycle state."""

        with self._session_lock(session_id):
            record = self.store.get_session(session_id)
            self._ensure_attachable(record)
            session = self._build_runtime_session(record)
            session.close()
            updated = StoredSession(info=session.describe(), config=record.config)
            self.store.save_session(updated)
            return updated

    def list_artifacts(self, run_id: str) -> tuple[ArtifactMetadata, ...]:
        """Return the artifact manifest recorded for one run."""

        return self.store.get_run(run_id).artifacts

    def show_artifact(
        self,
        run_id: str,
        path: str,
        *,
        max_chars: int | None = None,
    ) -> ArtifactPreview:
        """Re-attach the owning session and read a text preview for one artifact."""

        run = self.store.get_run(run_id)
        with self._session_lock(run.session_id):
            artifact = self._resolve_artifact(run.artifacts, path)
            record = self.store.get_session(run.session_id)
            self._ensure_attachable(record)
            session = self._build_runtime_session(record)
            try:
                preview = session.read_artifact_text(artifact.path, max_chars=max_chars)
            finally:
                self._finalize_session(session, record)
            return preview

    def download_artifact(self, run_id: str, path: str, destination: str | Path) -> Path:
        """Re-attach the owning session and download one recorded artifact."""

        run = self.store.get_run(run_id)
        with self._session_lock(run.session_id):
            artifact = self._resolve_artifact(run.artifacts, path)
            record = self.store.get_session(run.session_id)
            self._ensure_attachable(record)
            session = self._build_runtime_session(record)
            try:
                downloaded = session.download_artifact(artifact.path, destination)
            finally:
                self._finalize_session(session, record)
            return downloaded

    def _build_runtime_session(self, record: StoredSession) -> SandboxSession:
        """Recreate a runtime session from persisted state for one managed operation."""

        sandbox_id = record.info.sandbox_id
        if sandbox_id is None:
            raise SessionError(
                f"Stored session {record.info.session_id!r} has no sandbox_id "
                "and cannot be re-attached."
            )
        return SandboxSession.attach(
            sandbox_id,
            record.config,
            session_id=record.info.session_id,
            initial_run_sequence=record.info.run_count,
            created_at=record.info.created_at,
            last_run_id=record.info.last_run_id,
        )

    def _ensure_attachable(self, record: StoredSession) -> None:
        """Reject stored sessions that have already been terminated."""

        if record.info.status is SessionStatus.TERMINATED:
            raise SessionError(
                f"Stored session {record.info.session_id!r} is terminated and cannot be reused."
            )

    def _resolve_artifact(
        self,
        artifacts: tuple[ArtifactMetadata, ...],
        path: str,
    ) -> ArtifactMetadata:
        """Match a user-supplied artifact path against recorded run metadata."""

        normalized = path.lstrip("/")
        for artifact in artifacts:
            if path in {artifact.path, artifact.remote_path} or normalized == artifact.path:
                return artifact
        raise ArtifactNotFoundError(
            f"Artifact {path!r} was not found in the recorded artifacts for this run."
        )

    def _finalize_session(self, session: SandboxSession, record: StoredSession) -> None:
        """Persist post-run state and detach the runtime session for later reuse."""

        if session.status is not SessionStatus.ACTIVE:
            return
        self.store.save_session(StoredSession(info=session.describe(), config=record.config))
        try:
            session.detach()
        except Exception as exc:
            raise SessionError(
                f"Failed to detach session {record.info.session_id!r} after operation."
            ) from exc
        self.store.save_session(StoredSession(info=session.describe(), config=record.config))

    @contextlib.contextmanager
    def _session_lock(self, session_id: str) -> Iterator[None]:
        """Serialize managed work for one session across processes."""

        lock_path = self.store.sessions_dir / f".{session_id}.lock"
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
