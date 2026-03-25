from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("MODAL_RUN_INTEGRATION") != "1",
        reason="Set MODAL_RUN_INTEGRATION=1 to enable Modal integration tests.",
    ),
]

pytest.importorskip("modal")

from agent_sandbox import ExecutionStatus, ModalSandboxConfig, SandboxSession


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

        shell_result = session.run_shell("cat note.txt")
        assert shell_result.status is ExecutionStatus.SUCCEEDED
        assert shell_result.stdout.strip() == "hello from modal"


def test_timeout_returns_structured_result(config: ModalSandboxConfig) -> None:
    with SandboxSession(config) as session:
        result = session.run_python("import time\ntime.sleep(5)", timeout_seconds=1)
        assert result.status is ExecutionStatus.TIMED_OUT
        assert result.success is False
