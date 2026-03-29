"""State-store tests for JSON persistence and concurrent write safety."""

from __future__ import annotations

import threading
from pathlib import Path

from agent_sandbox.config import ModalSandboxConfig
from agent_sandbox.models import (
    ExecutionKind,
    ExecutionResult,
    ExecutionStatus,
    SessionInfo,
    SessionStatus,
)
from agent_sandbox.state import LocalStateStore, StoredSession


def test_local_state_store_round_trips_session_and_run(tmp_path: Path) -> None:
    store = LocalStateStore(tmp_path)
    session = StoredSession(
        info=SessionInfo(
            session_id="sess-1",
            sandbox_id="sb-1",
            app_name="demo",
            working_dir="/workspace",
            status=SessionStatus.DETACHED,
            run_count=1,
            last_run_id="run-1",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:01Z",
        ),
        config=ModalSandboxConfig(app_name="demo"),
    )
    run = ExecutionResult(
        run_id="run-1",
        sequence_number=1,
        kind=ExecutionKind.SHELL,
        status=ExecutionStatus.SUCCEEDED,
        success=True,
        command=("echo", "hello"),
        stdout="hello\n",
        session_id="sess-1",
        sandbox_id="sb-1",
        started_at="2026-01-01T00:00:00Z",
        completed_at="2026-01-01T00:00:01Z",
        duration_seconds=1.0,
    )

    store.save_session(session)
    store.save_run(run)

    assert store.get_session("sess-1").info.sandbox_id == "sb-1"
    assert store.get_run("run-1").stdout == "hello\n"
    assert len(store.list_sessions()) == 1
    assert len(store.list_runs(session_id="sess-1")) == 1


def test_local_state_store_handles_concurrent_session_writes(tmp_path: Path) -> None:
    store = LocalStateStore(tmp_path)
    session = StoredSession(
        info=SessionInfo(
            session_id="sess-1",
            sandbox_id="sb-1",
            app_name="demo",
            working_dir="/workspace",
            status=SessionStatus.DETACHED,
            run_count=2,
            last_run_id="run-2",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:01Z",
        ),
        config=ModalSandboxConfig(app_name="demo"),
    )

    errors: list[BaseException] = []

    def worker() -> None:
        try:
            store.save_session(session)
        except BaseException as exc:  # pragma: no cover - defensive
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert store.get_session("sess-1").info.run_count == 2


def test_local_state_store_handles_concurrent_run_writes(tmp_path: Path) -> None:
    store = LocalStateStore(tmp_path)

    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            store.save_run(
                ExecutionResult(
                    run_id=f"run-{index}",
                    sequence_number=index,
                    kind=ExecutionKind.PYTHON,
                    status=ExecutionStatus.SUCCEEDED,
                    success=True,
                    stdout=f"{index}\n",
                    session_id="sess-1",
                    sandbox_id="sb-1",
                    started_at="2026-01-01T00:00:00Z",
                    completed_at="2026-01-01T00:00:01Z",
                    duration_seconds=1.0,
                )
            )
        except BaseException as exc:  # pragma: no cover - defensive
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(store.list_runs(session_id="sess-1")) == 8
