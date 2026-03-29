"""Manager tests for persisted reattach semantics and locking behavior."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from agent_sandbox.config import ModalSandboxConfig
from agent_sandbox.exceptions import SessionError
from agent_sandbox.manager import SandboxManager
from agent_sandbox.models import (
    ExecutionKind,
    ExecutionResult,
    ExecutionStatus,
    SessionInfo,
    SessionStatus,
)
from agent_sandbox.state import LocalStateStore, StoredSession


class FakeManagedSession:
    """Test double that behaves like a managed session across re-attach flows."""

    def __init__(
        self,
        config: ModalSandboxConfig,
        *,
        sandbox_id: str | None = None,
        session_id: str | None = None,
        initial_run_sequence: int = 0,
        created_at: datetime | None = None,
        last_run_id: str | None = None,
    ) -> None:
        self.config = config
        self._sandbox_id = sandbox_id or "sb-managed"
        self._session_id = session_id or "sess-managed"
        self._run_count = initial_run_sequence
        self._created_at = created_at or datetime.fromisoformat("2026-01-01T00:00:00+00:00")
        self._last_run_id = last_run_id
        self.status = SessionStatus.CREATED

    @classmethod
    def attach(
        cls, sandbox_id: str, config: ModalSandboxConfig, **kwargs: Any
    ) -> FakeManagedSession:
        session = cls(config, sandbox_id=sandbox_id, **kwargs)
        session.status = SessionStatus.ACTIVE
        return session

    def start(self) -> None:
        self.status = SessionStatus.ACTIVE
        return None

    def detach(self) -> None:
        self.status = SessionStatus.DETACHED

    def close(self) -> None:
        self.status = SessionStatus.TERMINATED

    def describe(self) -> SessionInfo:
        return SessionInfo(
            session_id=self._session_id,
            sandbox_id=self._sandbox_id,
            app_name=self.config.app_name,
            working_dir=self.config.working_dir,
            status=self.status,
            is_closed=self.status is SessionStatus.TERMINATED,
            run_count=self._run_count,
            last_run_id=self._last_run_id,
            created_at=self._created_at,
            updated_at="2026-01-01T00:00:02Z",
        )

    def run_python(self, code: str, *, timeout_seconds: int | None = None) -> ExecutionResult:
        _ = (code, timeout_seconds)
        self._run_count += 1
        self._last_run_id = f"run-{self._run_count}"
        return ExecutionResult(
            run_id=self._last_run_id,
            sequence_number=self._run_count,
            kind=ExecutionKind.PYTHON,
            status=ExecutionStatus.SUCCEEDED,
            success=True,
            stdout="ok\n",
            session_id=self._session_id,
            sandbox_id=self._sandbox_id,
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:00:01Z",
            duration_seconds=1.0,
        )

    def read_artifact_text(self, path: str, *, max_chars: int | None = None) -> Any:
        raise AssertionError("not used in this test")

    def download_artifact(self, path: str, destination: str | Path) -> Path:
        raise AssertionError("not used in this test")


class ConcurrentManagedSession(FakeManagedSession):
    """Managed-session double that sleeps to force lock contention in tests."""

    def run_python(self, code: str, *, timeout_seconds: int | None = None) -> ExecutionResult:
        time.sleep(0.05)
        return super().run_python(code, timeout_seconds=timeout_seconds)


class DetachFailSession(FakeManagedSession):
    """Managed-session double that simulates detach failures after a run."""

    def detach(self) -> None:
        raise RuntimeError("detach failed")


def test_manager_preserves_created_at_when_reattaching(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("agent_sandbox.manager.SandboxSession", FakeManagedSession)

    store = LocalStateStore(tmp_path)
    record = StoredSession(
        info=SessionInfo(
            session_id="sess-1",
            sandbox_id="sb-1",
            app_name="demo",
            working_dir="/workspace",
            status=SessionStatus.DETACHED,
            run_count=3,
            last_run_id="run-3",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:01Z",
        ),
        config=ModalSandboxConfig(app_name="demo"),
    )
    store.save_session(record)

    manager = SandboxManager(store)
    result = manager.run_python("sess-1", "print('ok')")
    updated = store.get_session("sess-1")

    assert result.sequence_number == 4
    assert updated.info.created_at.isoformat() == "2026-01-01T00:00:00+00:00"
    assert updated.info.last_run_id == "run-4"


def test_manager_serializes_concurrent_runs_and_updates_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("agent_sandbox.manager.SandboxSession", ConcurrentManagedSession)

    store = LocalStateStore(tmp_path)
    store.save_session(
        StoredSession(
            info=SessionInfo(
                session_id="sess-1",
                sandbox_id="sb-1",
                app_name="demo",
                working_dir="/workspace",
                status=SessionStatus.DETACHED,
                run_count=3,
                last_run_id="run-3",
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:01Z",
            ),
            config=ModalSandboxConfig(app_name="demo"),
        )
    )

    manager = SandboxManager(store)
    results: list[ExecutionResult] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            results.append(manager.run_python("sess-1", "print('ok')"))
        except BaseException as exc:  # pragma: no cover - defensive
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    sequence_numbers = sorted(result.sequence_number for result in results)
    assert sequence_numbers == [4, 5]
    updated = store.get_session("sess-1")
    assert updated.info.run_count == 5
    assert updated.info.last_run_id in {result.run_id for result in results}
    assert len(store.list_runs(session_id="sess-1")) == 2


def test_manager_surfaces_detach_failures(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("agent_sandbox.manager.SandboxSession", DetachFailSession)

    store = LocalStateStore(tmp_path)
    store.save_session(
        StoredSession(
            info=SessionInfo(
                session_id="sess-1",
                sandbox_id="sb-1",
                app_name="demo",
                working_dir="/workspace",
                status=SessionStatus.DETACHED,
                run_count=3,
                last_run_id="run-3",
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:01Z",
            ),
            config=ModalSandboxConfig(app_name="demo"),
        )
    )

    manager = SandboxManager(store)

    with pytest.raises(SessionError, match="Failed to detach session"):
        manager.run_python("sess-1", "print('ok')")

    updated = store.get_session("sess-1")
    assert updated.info.status is SessionStatus.ACTIVE
    assert updated.info.run_count == 4
