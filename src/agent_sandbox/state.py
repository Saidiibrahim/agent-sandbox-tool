"""Local JSON-backed persistence for sessions and recorded runs.

The state store is intentionally simple so CLI and service workflows can reuse
detached sandboxes across processes without a daemon or database.
"""

from __future__ import annotations

import os
import tempfile
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

from .config import ModalSandboxConfig
from .exceptions import RunNotFoundError, SessionNotFoundError, StateStoreError
from .models import ExecutionResult, SessionInfo


class StoredSession(BaseModel):
    """Persisted pairing of session lifecycle info and its originating config."""

    model_config = ConfigDict(extra="forbid")

    info: SessionInfo
    config: ModalSandboxConfig


ModelT = TypeVar("ModelT", bound=BaseModel)


class LocalStateStore:
    """Simple JSON-backed store for sessions and runs.

    Writes are serialized with a process-local lock and committed via
    temp-file replacement so concurrent CLI/service operations do not leave
    partially written JSON behind.
    """

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        env_root = os.getenv("AGENT_SANDBOX_HOME")
        base_value: str | os.PathLike[str] = (
            root if root is not None else env_root or "~/.agent-sandbox-modal"
        )
        base = Path(base_value).expanduser()
        self.root = base
        self.sessions_dir = self.root / "sessions"
        self.runs_dir = self.root / "runs"
        self._lock = threading.RLock()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, record: StoredSession) -> StoredSession:
        """Persist the latest lifecycle snapshot for a session."""

        with self._lock:
            self._write_json(self.sessions_dir / f"{record.info.session_id}.json", record)
            return record

    def get_session(self, session_id: str) -> StoredSession:
        """Load one stored session record by ``session_id``."""

        with self._lock:
            path = self.sessions_dir / f"{session_id}.json"
            if not path.exists():
                raise SessionNotFoundError(
                    f"No stored session exists for session_id={session_id!r}."
                )
            return self._read_model(path, StoredSession)

    def list_sessions(self) -> list[StoredSession]:
        """List stored sessions ordered by most recently updated first."""

        with self._lock:
            return sorted(
                (
                    self._read_model(path, StoredSession)
                    for path in self._iter_json(self.sessions_dir)
                ),
                key=lambda record: record.info.updated_at,
                reverse=True,
            )

    def save_run(self, result: ExecutionResult) -> ExecutionResult:
        """Persist a completed execution result by ``run_id``."""

        with self._lock:
            self._write_json(self.runs_dir / f"{result.run_id}.json", result)
            return result

    def get_run(self, run_id: str) -> ExecutionResult:
        """Load one stored run by ``run_id``."""

        with self._lock:
            path = self.runs_dir / f"{run_id}.json"
            if not path.exists():
                raise RunNotFoundError(f"No stored run exists for run_id={run_id!r}.")
            return self._read_model(path, ExecutionResult)

    def list_runs(self, *, session_id: str | None = None) -> list[ExecutionResult]:
        """List recorded runs, optionally filtered to one session."""

        with self._lock:
            runs = [
                self._read_model(path, ExecutionResult) for path in self._iter_json(self.runs_dir)
            ]
            if session_id is not None:
                runs = [run for run in runs if run.session_id == session_id]
            return sorted(runs, key=lambda run: run.started_at, reverse=True)

    def _iter_json(self, directory: Path) -> Iterable[Path]:
        yield from directory.glob("*.json")

    def _read_model(self, path: Path, model_type: type[ModelT]) -> ModelT:
        """Read one JSON file and validate it as the requested Pydantic model."""

        try:
            return model_type.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            raise StateStoreError(f"Failed to read state file {str(path)!r}: {exc}") from exc

    def _write_json(self, path: Path, model: BaseModel) -> None:
        """Write JSON atomically via a unique temp file in the target directory."""

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f"{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_file.write(model.model_dump_json(indent=2))
                temp_path = Path(temp_file.name)
            temp_path.replace(path)
        except Exception as exc:  # pragma: no cover - defensive
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass
            raise StateStoreError(f"Failed to write state file {str(path)!r}: {exc}") from exc
