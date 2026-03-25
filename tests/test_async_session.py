from __future__ import annotations

import pytest

from agent_sandbox.config import ModalSandboxConfig
from agent_sandbox.execution.protocol import PythonExecutionResponse
from agent_sandbox.models import ExecutionStatus
from agent_sandbox.session import AsyncSandboxSession

from .fakes import FakeAsyncBackend, backend_result


@pytest.mark.asyncio
async def test_async_session_maps_python_results() -> None:
    protocol = PythonExecutionResponse(success=True, stdout="async\n", value_repr="3").model_dump_json()
    backend = FakeAsyncBackend(
        queue=[backend_result(stdout=protocol, command=("python", "-u", "-c", "runner"))]
    )
    session = AsyncSandboxSession(ModalSandboxConfig(), backend=backend)

    result = await session.run_python("print('async')\n1 + 2")

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.value_repr == "3"
