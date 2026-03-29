"""Regression tests for run metadata and artifact access semantics."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_sandbox.config import ModalSandboxConfig
from agent_sandbox.exceptions import ArtifactError
from agent_sandbox.execution.protocol import PythonExecutionResponse
from agent_sandbox.session import SandboxSession

from .fakes import FakeBackend, backend_result


def test_session_records_run_metadata() -> None:
    protocol = PythonExecutionResponse(
        success=True, stdout="hello\n", value_repr="4"
    ).model_dump_json()
    backend = FakeBackend(
        queue=[backend_result(stdout=protocol, command=("python", "-u", "-c", "runner"))]
    )
    session = SandboxSession(ModalSandboxConfig(), backend=backend)

    result = session.run_python("print('hello')\n2 + 2")
    info = session.describe()

    assert result.run_id
    assert result.sequence_number == 1
    assert info.run_count == 1
    assert info.last_run_id == result.run_id


def test_artifact_preview_and_download(tmp_path: Path) -> None:
    backend = FakeBackend(files={"/workspace/report.txt": "hello from artifact"})
    session = SandboxSession(ModalSandboxConfig(), backend=backend)
    session.start()

    preview = session.read_artifact_text("report.txt", max_chars=5)
    destination = session.download_artifact("report.txt", tmp_path / "report.txt")

    assert preview.path == "report.txt"
    assert preview.preview == "hello"
    assert preview.truncated is True
    assert destination.read_text(encoding="utf-8") == "hello from artifact"


def test_artifact_path_cannot_escape_working_dir() -> None:
    backend = FakeBackend(files={"/workspace/report.txt": "hello from artifact"})
    session = SandboxSession(ModalSandboxConfig(), backend=backend)
    session.start()

    with pytest.raises(ArtifactError):
        session.read_artifact_text("../report.txt")
