#!/usr/bin/env python3
"""Generate docs/generated/db-schema.md from the repo's typed Pydantic schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_sandbox.config import ModalSandboxConfig, NetworkPolicy  # noqa: E402
from agent_sandbox.execution.protocol import (  # noqa: E402
    PythonExecutionRequest,
    PythonExecutionResponse,
)
from agent_sandbox.models import (  # noqa: E402
    ArtifactMetadata,
    ArtifactPreview,
    ExecutionResult,
    SandboxHandle,
    SessionInfo,
)

OUTPUT_PATH = ROOT / "docs" / "generated" / "db-schema.md"
MODELS = [
    ("Configuration", ModalSandboxConfig),
    ("Configuration", NetworkPolicy),
    ("Execution Protocol", PythonExecutionRequest),
    ("Execution Protocol", PythonExecutionResponse),
    ("Shared Models", SandboxHandle),
    ("Shared Models", SessionInfo),
    ("Shared Models", ArtifactMetadata),
    ("Shared Models", ArtifactPreview),
    ("Shared Models", ExecutionResult),
]


def _format_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    if "anyOf" in schema:
        return " | ".join(_format_type(item) for item in schema["anyOf"])
    if "enum" in schema:
        return "enum"
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return " | ".join(str(item) for item in schema_type)
    if schema_type == "array":
        return f"array<{_format_type(schema.get('items', {}))}>"
    if schema_type == "object":
        return "object"
    if schema_type is None:
        return "unknown"
    return str(schema_type)


def _render_model(heading: str, model: type[Any]) -> str:
    schema = model.model_json_schema()
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    lines = [f"## {model.__name__}", "", f"- Domain: {heading}", ""]

    if props:
        lines.extend(
            [
                "| Field | Type | Required | Notes |",
                "| --- | --- | --- | --- |",
            ]
        )
        for field_name, field_schema in props.items():
            notes: list[str] = []
            if "default" in field_schema:
                notes.append(f"default={json.dumps(field_schema['default'])}")
            if "description" in field_schema:
                notes.append(str(field_schema["description"]))
            if "enum" in field_schema:
                notes.append("enum=" + ", ".join(map(str, field_schema["enum"])))
            lines.append(
                "| "
                + " | ".join(
                    [
                        field_name,
                        _format_type(field_schema),
                        "yes" if field_name in required else "no",
                        "; ".join(notes) if notes else "-",
                    ]
                )
                + " |"
            )
        lines.append("")

    defs = schema.get("$defs", {})
    if defs:
        lines.append("### Referenced Definitions")
        lines.append("")
        for def_name, def_schema in defs.items():
            lines.append(f"- `{def_name}`: {_format_type(def_schema)}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    sections = [
        "# Generated Schema Reference",
        "",
        "This repository does not define a relational database schema. "
        "This generated file documents the current typed schema sources "
        "that act as the authoritative machine-readable contract for "
        "config, protocol, and execution results.",
        "",
        "## Regeneration",
        "",
        "Run from the repository root after installing dependencies:",
        "",
        "```bash",
        "PYTHONPATH=src ./.venv/bin/python scripts/generate_db_schema.py",
        "```",
        "",
    ]

    current_heading = None
    for heading, model in MODELS:
        if heading != current_heading:
            sections.extend([f"## {heading}", ""])
            current_heading = heading
        sections.append(_render_model(heading, model))

    OUTPUT_PATH.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
