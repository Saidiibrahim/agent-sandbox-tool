"""CLI contract tests for JSON output, exit codes, and serve wiring."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from agent_sandbox.cli import (
    EXIT_CONFIG,
    EXIT_LIFECYCLE,
    EXIT_MODAL,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_RUN_FAILED,
    EXIT_USAGE,
    main,
)
from agent_sandbox.config import ModalSandboxConfig
from agent_sandbox.diagnostics import ModalEnvironmentReport
from agent_sandbox.models import (
    ExecutionKind,
    ExecutionResult,
    ExecutionStatus,
    SessionInfo,
    SessionStatus,
)
from agent_sandbox.state import LocalStateStore, StoredSession


def test_cli_doctor_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "agent_sandbox.cli.validate_modal_environment",
        lambda **kwargs: ModalEnvironmentReport(
            ok=False,
            modal_installed=False,
            auth_configured=False,
            messages=("missing modal",),
            recommended_actions=("install modal",),
        ),
    )

    exit_code = main(["--json", "doctor"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == EXIT_MODAL
    assert payload["ok"] is False


def test_cli_json_usage_errors_are_structured(capsys) -> None:
    exit_code = main(["--json", "run", "python"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == EXIT_USAGE
    assert captured.err == ""
    assert payload["error"]["type"] == "UsageError"
    assert "usage:" in payload["usage"].lower()


def test_cli_run_show_missing_state(tmp_path: Path, capsys) -> None:
    exit_code = main(["--json", "--state-dir", str(tmp_path), "run", "show", "missing-run"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == EXIT_NOT_FOUND
    assert payload["error"]["type"] == "RunNotFoundError"


def test_cli_session_start_rejects_unsupported_ephemeral_disk_mb(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(
        "agent_sandbox.cli.validate_modal_environment",
        lambda **kwargs: ModalEnvironmentReport(
            ok=True,
            modal_installed=True,
            modal_version="1.0.0",
            auth_configured=True,
        ),
    )

    exit_code = main(
        [
            "--json",
            "--state-dir",
            str(tmp_path),
            "session",
            "start",
            "--ephemeral-disk-mb",
            "64",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == EXIT_CONFIG
    assert payload["error"]["type"] == "ConfigurationError"
    assert "ephemeral_disk_mb" in payload["error"]["message"]


def test_cli_session_start_reports_modal_config_errors(monkeypatch, tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "modal.toml"
    config_path.write_text("[profiles", encoding="utf-8")

    def fake_import_module(name: str):
        if name == "modal":

            class DummyModal:
                __name__ = "modal"

            return DummyModal()
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr("agent_sandbox.diagnostics.importlib.import_module", fake_import_module)
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    monkeypatch.setenv("MODAL_CONFIG_PATH", str(config_path))

    exit_code = main(["--json", "--state-dir", str(tmp_path), "session", "start"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == EXIT_MODAL
    assert payload["error"]["type"] == "ModalConfigurationError"
    assert "invalid toml" in payload["error"]["message"].lower()


def test_cli_session_terminate_maps_lifecycle_errors(monkeypatch, tmp_path: Path, capsys) -> None:
    store = LocalStateStore(tmp_path)
    now = datetime.now(UTC)
    store.save_session(
        StoredSession(
            info=SessionInfo(
                session_id="sess-term",
                sandbox_id="sandbox-1",
                app_name="agent-sandbox",
                working_dir="/workspace",
                status=SessionStatus.TERMINATED,
                is_closed=True,
                run_count=0,
                created_at=now,
                updated_at=now,
            ),
            config=ModalSandboxConfig(),
        )
    )
    monkeypatch.setattr(
        "agent_sandbox.cli.validate_modal_environment",
        lambda **kwargs: ModalEnvironmentReport(
            ok=True,
            modal_installed=True,
            modal_version="1.0.0",
            auth_configured=True,
        ),
    )

    exit_code = main(["--json", "--state-dir", str(tmp_path), "session", "terminate", "sess-term"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == EXIT_LIFECYCLE
    assert captured.err == ""
    assert payload["error"]["type"] == "SessionError"


def test_cli_serve_uses_cli_state_dir_and_skips_modal_gate(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    import agent_sandbox.server.app as server_app

    called: dict[str, object] = {}

    def fake_validate_modal_environment(**kwargs):
        raise AssertionError("Modal readiness should not be checked for serve")

    def fake_create_app(*, settings, manager, store):
        called["state_dir"] = settings.state_dir
        called["manager_root"] = manager.store.root
        called["store_root"] = store.root
        return "app-sentinel"

    def fake_run(app, host, port, log_level):
        called["app"] = app
        called["host"] = host
        called["port"] = port
        called["log_level"] = log_level

    monkeypatch.setattr(
        "agent_sandbox.cli.validate_modal_environment", fake_validate_modal_environment
    )
    monkeypatch.setattr(server_app, "create_app", fake_create_app)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=fake_run))

    exit_code = main(
        ["--json", "--state-dir", str(tmp_path), "serve", "--host", "0.0.0.0", "--port", "8123"]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == EXIT_OK
    assert payload == {"host": "0.0.0.0", "port": 8123}
    assert called["state_dir"] == str(tmp_path)
    assert called["manager_root"] == tmp_path
    assert called["store_root"] == tmp_path
    assert called["app"] == "app-sentinel"
    assert called["host"] == "0.0.0.0"
    assert called["port"] == 8123
    assert called["log_level"] == "info"


def test_cli_run_python_timeout_returns_structured_json_and_run_failed_exit(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    now = datetime.now(UTC)

    class FakeManager:
        def __init__(self, store):
            self.store = store

        def run_python(self, session_id: str, code: str, *, timeout_seconds: int | None = None):
            _ = (code, timeout_seconds)
            return ExecutionResult(
                kind=ExecutionKind.PYTHON,
                status=ExecutionStatus.TIMED_OUT,
                success=False,
                command=("python", "-u", "-c", "runner"),
                error_type="ExecTimeoutError",
                error_message="Command exceeded timeout of 1 seconds.",
                session_id=session_id,
                sandbox_id="sb-timeout",
                started_at=now,
                completed_at=now,
                duration_seconds=1.0,
            )

    monkeypatch.setattr(
        "agent_sandbox.cli.validate_modal_environment",
        lambda **kwargs: ModalEnvironmentReport(
            ok=True,
            modal_installed=True,
            modal_version="1.0.0",
            auth_configured=True,
        ),
    )
    monkeypatch.setattr("agent_sandbox.cli.SandboxManager", FakeManager)

    exit_code = main(
        [
            "--json",
            "--state-dir",
            str(tmp_path),
            "run",
            "python",
            "sess-timeout",
            "--code",
            "import time; time.sleep(5)",
            "--timeout-seconds",
            "1",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == EXIT_RUN_FAILED
    assert payload["status"] == "timed_out"
    assert payload["success"] is False
    assert payload["error_type"] == "ExecTimeoutError"
