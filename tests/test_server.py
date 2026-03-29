"""HTTP API tests for auth, dependency wiring, and domain-error mapping."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("pydantic_settings")

from fastapi.testclient import TestClient

from agent_sandbox.config import ModalSandboxConfig
from agent_sandbox.exceptions import (
    BackendError,
    ConfigurationError,
    ModalConfigurationError,
    RunNotFoundError,
    SessionError,
)
from agent_sandbox.models import (
    ArtifactChangeType,
    ArtifactMetadata,
    ArtifactPreview,
    ExecutionKind,
    ExecutionResult,
    ExecutionStatus,
    SessionInfo,
    SessionStatus,
)
from agent_sandbox.server.app import create_app
from agent_sandbox.server.settings import ServiceSettings
from agent_sandbox.state import LocalStateStore, StoredSession


class RecordingServerManager:
    """Manager double that records routed calls and injects configured failures."""

    def __init__(
        self,
        *,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.errors = errors or {}
        self.calls: list[str] = []
        self.record = StoredSession(
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
        self.run = ExecutionResult(
            run_id="run-1",
            sequence_number=1,
            kind=ExecutionKind.PYTHON,
            status=ExecutionStatus.SUCCEEDED,
            success=True,
            stdout="ok\n",
            session_id="sess-1",
            sandbox_id="sb-1",
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:00:01Z",
            duration_seconds=1.0,
            artifacts=(
                ArtifactMetadata(
                    path="report.txt",
                    remote_path="/workspace/report.txt",
                    size_bytes=5,
                    modified_at="2026-01-01T00:00:01Z",
                    change_type=ArtifactChangeType.ADDED,
                ),
            ),
        )

    def _maybe_raise(self, method_name: str) -> None:
        self.calls.append(method_name)
        exc = self.errors.get(method_name)
        if exc is not None:
            raise exc

    def start_session(self, config: ModalSandboxConfig) -> StoredSession:
        self._maybe_raise("start_session")
        return self.record

    def attach_session(self, sandbox_id: str, config: ModalSandboxConfig) -> StoredSession:
        self._maybe_raise("attach_session")
        return self.record

    def list_sessions(self) -> list[StoredSession]:
        self._maybe_raise("list_sessions")
        return [self.record]

    def get_session(self, session_id: str) -> StoredSession:
        self._maybe_raise("get_session")
        return self.record

    def run_python(
        self, session_id: str, code: str, *, timeout_seconds: int | None = None
    ) -> ExecutionResult:
        self._maybe_raise("run_python")
        return self.run

    def run_shell(
        self, session_id: str, command: str, *, timeout_seconds: int | None = None
    ) -> ExecutionResult:
        self._maybe_raise("run_shell")
        return self.run

    def terminate_session(self, session_id: str) -> StoredSession:
        self._maybe_raise("terminate_session")
        return self.record

    def list_runs(self, *, session_id: str | None = None) -> list[ExecutionResult]:
        self._maybe_raise("list_runs")
        return [self.run]

    def get_run(self, run_id: str) -> ExecutionResult:
        self._maybe_raise("get_run")
        if run_id != "run-1":
            raise RunNotFoundError(f"missing {run_id}")
        return self.run

    def list_artifacts(self, run_id: str) -> tuple[ArtifactMetadata, ...]:
        self._maybe_raise("list_artifacts")
        return self.run.artifacts

    def show_artifact(
        self, run_id: str, path: str, *, max_chars: int | None = None
    ) -> ArtifactPreview:
        self._maybe_raise("show_artifact")
        return ArtifactPreview(
            path="report.txt",
            remote_path="/workspace/report.txt",
            preview="hello",
            truncated=False,
            size_bytes=5,
        )


def test_server_health_and_auth() -> None:
    app = create_app(
        settings=ServiceSettings(bearer_token="secret"),
        manager=RecordingServerManager(),
    )
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        assert "x-request-id" in health.headers

        unauthorized = client.get("/sessions")
        assert unauthorized.status_code == 401


def test_server_uses_state_dir_backing_store(tmp_path: Path) -> None:
    store = LocalStateStore(tmp_path)
    store.save_session(
        StoredSession(
            info=SessionInfo(
                session_id="sess-store",
                sandbox_id="sb-store",
                app_name="demo",
                working_dir="/workspace",
                status=SessionStatus.DETACHED,
                run_count=0,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:01Z",
            ),
            config=ModalSandboxConfig(app_name="demo"),
        )
    )

    app = create_app(settings=ServiceSettings(state_dir=str(tmp_path), bearer_token="secret"))
    with TestClient(app) as client:
        response = client.get("/sessions", headers={"Authorization": "Bearer secret"})
        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["info"]["session_id"] == "sess-store"
        assert payload[0]["info"]["sandbox_id"] == "sb-store"


def test_server_routes_and_stateful_manager_calls() -> None:
    manager = RecordingServerManager()
    app = create_app(settings=ServiceSettings(bearer_token="secret"), manager=manager)
    headers = {"Authorization": "Bearer secret"}

    with TestClient(app) as client:
        create_response = client.post(
            "/sessions",
            json={"config": {"app_name": "demo"}},
            headers=headers,
        )
        assert create_response.status_code == 200

        attach_response = client.post(
            "/sessions/attach",
            json={"sandbox_id": "sb-2", "config": {"app_name": "demo"}},
            headers=headers,
        )
        assert attach_response.status_code == 200

        python_response = client.post(
            "/sessions/sess-1/runs/python",
            json={"code": "print('hi')", "timeout_seconds": 3},
            headers=headers,
        )
        assert python_response.status_code == 200
        assert python_response.json()["run_id"] == "run-1"

        shell_response = client.post(
            "/sessions/sess-1/runs/shell",
            json={"command": "echo hi", "timeout_seconds": 4},
            headers=headers,
        )
        assert shell_response.status_code == 200

        terminate_response = client.post(
            "/sessions/sess-1/terminate",
            headers=headers,
        )
        assert terminate_response.status_code == 200

        runs_response = client.get("/runs", headers=headers)
        assert runs_response.status_code == 200
        assert runs_response.json()["runs"][0]["run_id"] == "run-1"

        run_response = client.get("/runs/run-1", headers=headers)
        assert run_response.status_code == 200

        artifacts_response = client.get("/runs/run-1/artifacts", headers=headers)
        assert artifacts_response.status_code == 200
        assert artifacts_response.json()["artifacts"][0]["path"] == "report.txt"

        preview_response = client.get(
            "/runs/run-1/artifacts/preview",
            params={"path": "report.txt", "max_chars": 3},
            headers=headers,
        )
        assert preview_response.status_code == 200
        assert preview_response.json()["preview"] == "hello"

    assert manager.calls == [
        "start_session",
        "attach_session",
        "run_python",
        "run_shell",
        "terminate_session",
        "list_runs",
        "get_run",
        "list_artifacts",
        "show_artifact",
    ]


def test_server_maps_not_found_errors() -> None:
    app = create_app(
        settings=ServiceSettings(bearer_token="secret"),
        manager=RecordingServerManager(),
    )
    with TestClient(app) as client:
        response = client.get("/runs/missing", headers={"Authorization": "Bearer secret"})
        assert response.status_code == 404
        assert response.json()["error"]["type"] == "RunNotFoundError"


@pytest.mark.parametrize(
    ("method", "path", "payload", "params", "method_name", "exc", "status_code"),
    [
        (
            "post",
            "/sessions",
            {"config": {"app_name": "demo"}},
            None,
            "start_session",
            ConfigurationError("bad config"),
            400,
        ),
        (
            "post",
            "/sessions/sess-1/terminate",
            None,
            None,
            "terminate_session",
            SessionError("bad lifecycle"),
            409,
        ),
        (
            "post",
            "/sessions/sess-1/runs/python",
            {"code": "print('hi')"},
            None,
            "run_python",
            BackendError("backend failed"),
            502,
        ),
        (
            "get",
            "/runs/run-1/artifacts/preview",
            None,
            {"path": "report.txt"},
            "show_artifact",
            ModalConfigurationError("modal unavailable"),
            503,
        ),
    ],
)
def test_server_maps_domain_errors(
    method: str,
    path: str,
    payload: dict[str, object] | None,
    params: dict[str, object] | None,
    method_name: str,
    exc: Exception,
    status_code: int,
) -> None:
    manager = RecordingServerManager(errors={method_name: exc})
    app = create_app(settings=ServiceSettings(bearer_token="secret"), manager=manager)

    with TestClient(app) as client:
        response = client.request(
            method,
            path,
            json=payload,
            params=params,
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == status_code
    assert response.json()["error"]["type"] == type(exc).__name__
