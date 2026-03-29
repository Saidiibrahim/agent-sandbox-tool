"""Live Modal integration tests for the real backend implementation.

These tests are opt-in because they require Modal credentials and validate the
end-to-end lifecycle, artifact, and timeout behavior against the real service.
"""

from __future__ import annotations

import os

import pytest

from agent_sandbox import ExecutionStatus, ModalSandboxConfig, SandboxSession

pytest.importorskip("modal")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("MODAL_RUN_INTEGRATION") != "1",
        reason="Set MODAL_RUN_INTEGRATION=1 to enable Modal integration tests.",
    ),
]


@pytest.fixture()
def config() -> ModalSandboxConfig:
    return ModalSandboxConfig(
        app_name="agent-sandbox-modal-tests",
        idle_timeout_seconds=60,
        default_exec_timeout_seconds=20,
    )


def test_end_to_end_python_and_shell(config: ModalSandboxConfig) -> None:
    with SandboxSession(config) as session:
        py_result = session.run_python(
            """
from pathlib import Path
Path('note.txt').write_text('hello from modal')
'hello from modal'
"""
        )
        assert py_result.status is ExecutionStatus.SUCCEEDED
        assert py_result.value_repr == "'hello from modal'"
        assert any(artifact.path == "note.txt" for artifact in py_result.artifacts)

        preview = session.read_artifact_text("note.txt")
        assert preview.preview == "hello from modal"

        shell_result = session.run_shell("cat note.txt")
        assert shell_result.status is ExecutionStatus.SUCCEEDED
        assert shell_result.stdout.strip() == "hello from modal"


def test_timeout_returns_structured_result(config: ModalSandboxConfig) -> None:
    with SandboxSession(config) as session:
        for _ in range(3):
            result = session.run_python("import time\ntime.sleep(5)", timeout_seconds=1)
            assert result.status is ExecutionStatus.TIMED_OUT
            assert result.success is False
            assert result.error_type == "ExecTimeoutError"
            assert "timeout of 1 seconds" in (result.error_message or "") or "timeout boundary" in (
                result.error_message or ""
            )
            assert result.exit_code in (None, -1, 124, 137, 143)
