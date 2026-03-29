"""Tool wrapper tests for plain JSON payload serialization."""

from __future__ import annotations

from agent_sandbox.config import ModalSandboxConfig
from agent_sandbox.execution.protocol import PythonExecutionResponse
from agent_sandbox.session import SandboxSession
from agent_sandbox.tool import PythonSandboxTool

from .fakes import FakeBackend, backend_result


def test_tool_returns_plain_json_payload() -> None:
    protocol = PythonExecutionResponse(
        success=True, stdout="tool\n", value_repr="7"
    ).model_dump_json()
    backend = FakeBackend(
        queue=[backend_result(stdout=protocol, command=("python", "-u", "-c", "runner"))]
    )
    tool = PythonSandboxTool(SandboxSession(ModalSandboxConfig(), backend=backend))

    payload = tool("print('tool')\n3 + 4")

    assert payload["success"] is True
    assert payload["value_repr"] == "7"
