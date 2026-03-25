from __future__ import annotations

import subprocess
import sys

from agent_sandbox.execution.python_runner import (
    build_python_command,
    build_python_request,
    parse_python_response,
)


def _run_locally(code: str) -> tuple[subprocess.CompletedProcess[str], object]:
    request = build_python_request(
        code=code,
        working_dir=None,
        max_output_chars=10_000,
        max_value_repr_chars=5_000,
    )
    command = (sys.executable, *build_python_command()[1:])
    completed = subprocess.run(
        command,
        input=request.model_dump_json(),
        capture_output=True,
        text=True,
        check=False,
    )
    response = parse_python_response(completed.stdout)
    return completed, response


def test_runner_captures_stdout_and_final_expression() -> None:
    completed, response = _run_locally("print('hello')\n2 + 2")
    assert completed.returncode == 0
    assert response.success is True
    assert response.stdout == "hello\n"
    assert response.value_repr == "4"


def test_runner_captures_exceptions_without_crashing() -> None:
    completed, response = _run_locally("raise ValueError('boom')")
    assert completed.returncode == 0
    assert response.success is False
    assert response.error_type == "ValueError"
    assert "boom" in (response.error_message or "")
    assert "Traceback" in (response.traceback or "")
