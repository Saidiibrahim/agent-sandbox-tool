from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = 1


class PythonExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = PROTOCOL_VERSION
    code: str
    working_dir: str | None = None
    max_output_chars: int = Field(default=50_000, ge=512)
    max_value_repr_chars: int = Field(default=10_000, ge=128)


class PythonExecutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = PROTOCOL_VERSION
    success: bool
    runner_error: bool = False
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    value_repr: str | None = None
    value_repr_truncated: bool = False
    error_type: str | None = None
    error_message: str | None = None
    traceback: str | None = None
