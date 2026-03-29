"""Helpers for the structured Python execution path.

The host process injects a small bootstrap program into the sandbox so Python
execution returns one JSON payload instead of ad hoc stdout parsing. This file
builds the command/request pair and validates the structured response.
"""

from __future__ import annotations

import textwrap

from ..exceptions import ProtocolError
from .protocol import PythonExecutionRequest, PythonExecutionResponse

# The bootstrap script runs inside the sandbox and must emit exactly one JSON
# response on stdout so the host can parse results deterministically.
PYTHON_RUNNER_BOOTSTRAP = textwrap.dedent(
    r"""
    import ast
    import contextlib
    import io
    import json
    import os
    import sys
    import traceback

    PROTOCOL_VERSION = 1


    class TruncatingBuffer(io.TextIOBase):
        def __init__(self, limit):
            self.limit = int(limit)
            self.parts = []
            self.length = 0
            self.truncated = False

        def write(self, text):
            text = str(text)
            remaining = self.limit - self.length
            if remaining > 0:
                chunk = text[:remaining]
                self.parts.append(chunk)
                self.length += len(chunk)
            if len(text) > max(remaining, 0):
                self.truncated = True
            return len(text)

        def flush(self):
            return None

        def getvalue(self):
            return "".join(self.parts)


    def safe_repr(value):
        try:
            return repr(value)
        except BaseException as exc:
            return f"<repr failed: {type(exc).__name__}: {exc}>"


    def clamp(text, limit):
        if text is None:
            return None, False
        if len(text) <= limit:
            return text, False
        return text[:limit], True


    def split_last_expression(code):
        module = ast.parse(code, mode="exec")
        tail = None
        if module.body and isinstance(module.body[-1], ast.Expr):
            tail = ast.Expression(module.body.pop().value)
            ast.fix_missing_locations(tail)
        return module, tail


    def emit(payload):
        sys.stdout.write(json.dumps(payload))
        sys.stdout.flush()


    def protocol_failure(error_type, error_message, traceback_text=None):
        return {
            "protocol_version": PROTOCOL_VERSION,
            "success": False,
            "runner_error": True,
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "value_repr": None,
            "value_repr_truncated": False,
            "error_type": error_type,
            "error_message": error_message,
            "traceback": traceback_text,
        }


    def main():
        raw = sys.stdin.read()
        if not raw:
            emit(protocol_failure("ProtocolError", "No JSON request payload received on stdin."))
            return 70

        request = json.loads(raw)
        if request.get("protocol_version") != PROTOCOL_VERSION:
            emit(
                protocol_failure(
                    "ProtocolError",
                    f"Unsupported protocol version: {request.get('protocol_version')}",
                )
            )
            return 70

        code = request.get("code", "")
        working_dir = request.get("working_dir")
        max_output_chars = int(request.get("max_output_chars", 50000))
        max_value_repr_chars = int(request.get("max_value_repr_chars", 10000))

        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            os.chdir(working_dir)

        stdout_buffer = TruncatingBuffer(max_output_chars)
        stderr_buffer = TruncatingBuffer(max_output_chars)
        namespace = {"__name__": "__main__"}
        success = True
        error_type = None
        error_message = None
        traceback_text = None
        value_repr = None
        value_repr_truncated = False

        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            try:
                module, tail = split_last_expression(code)
                exec(compile(module, "<agent-sandbox>", "exec"), namespace, namespace)
                if tail is not None:
                    value = eval(compile(tail, "<agent-sandbox>", "eval"), namespace, namespace)
                    if value is not None:
                        value_repr, value_repr_truncated = clamp(
                            safe_repr(value), max_value_repr_chars
                        )
            except BaseException as exc:
                success = False
                error_type = type(exc).__name__
                error_message = str(exc)
                traceback_text, _ = clamp(traceback.format_exc(), max_output_chars)

        emit(
            {
                "protocol_version": PROTOCOL_VERSION,
                "success": success,
                "runner_error": False,
                "stdout": stdout_buffer.getvalue(),
                "stderr": stderr_buffer.getvalue(),
                "stdout_truncated": stdout_buffer.truncated,
                "stderr_truncated": stderr_buffer.truncated,
                "value_repr": value_repr,
                "value_repr_truncated": value_repr_truncated,
                "error_type": error_type,
                "error_message": error_message,
                "traceback": traceback_text,
            }
        )
        return 0


    if __name__ == "__main__":
        try:
            exit_code = main()
        except BaseException as exc:
            emit(
                protocol_failure(
                    type(exc).__name__,
                    str(exc),
                    traceback.format_exc(),
                )
            )
            raise
        raise SystemExit(exit_code)
    """
).strip()


def build_python_command() -> tuple[str, str, str, str]:
    """Return the interpreter command that runs the bootstrap inside a sandbox."""

    return ("python", "-u", "-c", PYTHON_RUNNER_BOOTSTRAP)


def build_python_request(
    *,
    code: str,
    working_dir: str | None,
    max_output_chars: int,
    max_value_repr_chars: int,
) -> PythonExecutionRequest:
    """Build a validated request payload for one Python execution."""

    return PythonExecutionRequest(
        code=code,
        working_dir=working_dir,
        max_output_chars=max_output_chars,
        max_value_repr_chars=max_value_repr_chars,
    )


def parse_python_response(stdout: str) -> PythonExecutionResponse:
    """Parse the bootstrap's JSON response from stdout.

    The parser tolerates extra log lines by consuming the last non-empty line,
    but it still requires that the final payload validate against the versioned
    response model.
    """

    payload = stdout.strip()
    if not payload:
        raise ProtocolError("Python runner did not return a JSON payload on stdout.")

    if "\n" in payload:
        lines = [line for line in payload.splitlines() if line.strip()]
        payload = lines[-1]

    try:
        return PythonExecutionResponse.model_validate_json(payload)
    except Exception as exc:  # pragma: no cover - covered by ProtocolError contract
        raise ProtocolError(f"Malformed Python runner response: {payload!r}") from exc
