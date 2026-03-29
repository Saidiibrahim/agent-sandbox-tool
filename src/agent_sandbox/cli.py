"""Command-line operator surface for managed sandbox sessions.

The CLI is a thin layer over ``SandboxManager``. It preserves domain-specific
exit codes, supports machine-readable JSON output, and avoids checking Modal
readiness for commands that only inspect local state.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

from pydantic import ValidationError

from . import __version__
from .config import ModalSandboxConfig, NetworkMode, NetworkPolicy
from .diagnostics import validate_modal_environment
from .exceptions import (
    AgentSandboxError,
    ArtifactNotFoundError,
    BackendError,
    ConfigurationError,
    ModalConfigurationError,
    RunNotFoundError,
    SessionError,
    SessionNotFoundError,
)
from .logging import configure_basic_logging
from .manager import SandboxManager
from .models import ExecutionResult, ExecutionStatus
from .state import LocalStateStore, StoredSession

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_RUN_FAILED = 10
EXIT_NOT_FOUND = 11
EXIT_CONFIG = 12
EXIT_MODAL = 13
EXIT_BACKEND = 14
EXIT_INTERNAL = 15
EXIT_LIFECYCLE = 16


class UsageError(Exception):
    """Raised when argparse rejects the CLI invocation."""


class _ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser variant that raises ``UsageError`` instead of exiting."""

    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level ``agent-sandbox`` argument parser."""

    parser = _ArgumentParser(
        prog="agent-sandbox",
        description="Embeddable Modal sandbox tooling for developers and coding agents.",
    )
    parser.add_argument(
        "--json", dest="json_mode", action="store_true", help="emit machine-readable JSON"
    )
    parser.add_argument(
        "--state-dir",
        default=None,
        help="directory for persisted session/run state (default: ~/.agent-sandbox-modal)",
    )
    parser.add_argument("--log-level", default="WARNING")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=_ArgumentParser)

    doctor = subparsers.add_parser("doctor", help="validate the local Modal environment")
    doctor.set_defaults(func=_cmd_doctor)

    session = subparsers.add_parser(
        "session", help="create, inspect, and terminate sandbox sessions"
    )
    session_sub = session.add_subparsers(
        dest="session_command", required=True, parser_class=_ArgumentParser
    )

    session_start = session_sub.add_parser("start", help="create a new sandbox session")
    _add_config_args(session_start)
    session_start.set_defaults(func=_cmd_session_start)

    session_attach = session_sub.add_parser(
        "attach", help="register an existing sandbox by sandbox_id"
    )
    session_attach.add_argument("sandbox_id")
    _add_config_args(session_attach)
    session_attach.set_defaults(func=_cmd_session_attach)

    session_show = session_sub.add_parser("show", help="show one stored session")
    session_show.add_argument("session_id")
    session_show.set_defaults(func=_cmd_session_show)

    session_list = session_sub.add_parser("list", help="list stored sessions")
    session_list.set_defaults(func=_cmd_session_list)

    session_terminate = session_sub.add_parser(
        "terminate", help="terminate a stored sandbox session"
    )
    session_terminate.add_argument("session_id")
    session_terminate.set_defaults(func=_cmd_session_terminate)

    run = subparsers.add_parser("run", help="execute code or inspect stored runs")
    run_sub = run.add_subparsers(dest="run_command", required=True, parser_class=_ArgumentParser)

    run_python = run_sub.add_parser("python", help="run Python code inside a stored session")
    run_python.add_argument("session_id")
    code_group = run_python.add_mutually_exclusive_group(required=True)
    code_group.add_argument("--code")
    code_group.add_argument("--file")
    run_python.add_argument("--timeout-seconds", type=int, default=None)
    run_python.set_defaults(func=_cmd_run_python)

    run_shell = run_sub.add_parser("shell", help="run a shell command inside a stored session")
    run_shell.add_argument("session_id")
    run_shell.add_argument("command_text")
    run_shell.add_argument("--timeout-seconds", type=int, default=None)
    run_shell.set_defaults(func=_cmd_run_shell)

    run_show = run_sub.add_parser("show", help="show one stored run")
    run_show.add_argument("run_id")
    run_show.set_defaults(func=_cmd_run_show)

    run_list = run_sub.add_parser("list", help="list stored runs")
    run_list.add_argument("--session-id", default=None)
    run_list.set_defaults(func=_cmd_run_list)

    artifact = subparsers.add_parser("artifact", help="inspect artifacts produced by recorded runs")
    artifact_sub = artifact.add_subparsers(
        dest="artifact_command", required=True, parser_class=_ArgumentParser
    )

    artifact_list = artifact_sub.add_parser("list", help="list artifacts recorded for a run")
    artifact_list.add_argument("run_id")
    artifact_list.set_defaults(func=_cmd_artifact_list)

    artifact_show = artifact_sub.add_parser(
        "show", help="show text preview for a recorded artifact"
    )
    artifact_show.add_argument("run_id")
    artifact_show.add_argument("path")
    artifact_show.add_argument("--max-chars", type=int, default=None)
    artifact_show.set_defaults(func=_cmd_artifact_show)

    artifact_download = artifact_sub.add_parser(
        "download", help="download a recorded artifact to a local path"
    )
    artifact_download.add_argument("run_id")
    artifact_download.add_argument("path")
    artifact_download.add_argument("destination")
    artifact_download.set_defaults(func=_cmd_artifact_download)

    serve = subparsers.add_parser("serve", help="start the optional FastAPI service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_cmd_serve)

    return parser


def _add_config_args(parser: argparse.ArgumentParser) -> None:
    """Register shared sandbox configuration flags for session-creation commands."""

    parser.add_argument("--app-name", default="agent-sandbox")
    parser.add_argument("--python-version", default="3.11")
    parser.add_argument("--package", dest="python_packages", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=int, default=30 * 60)
    parser.add_argument("--idle-timeout-seconds", type=int, default=5 * 60)
    parser.add_argument("--default-exec-timeout-seconds", type=int, default=120)
    parser.add_argument("--working-dir", default="/workspace")
    parser.add_argument("--shell-executable", default="/bin/bash")
    parser.add_argument("--max-output-chars", type=int, default=50_000)
    parser.add_argument("--max-value-repr-chars", type=int, default=10_000)
    parser.add_argument("--artifact-max-preview-chars", type=int, default=10_000)
    parser.add_argument("--no-capture-artifacts", dest="capture_artifacts", action="store_false")
    parser.set_defaults(capture_artifacts=True)
    parser.add_argument("--cpu", type=float, default=None)
    parser.add_argument("--memory-mb", type=int, default=None)
    parser.add_argument("--ephemeral-disk-mb", type=int, default=None)
    parser.add_argument(
        "--network",
        choices=[mode.value for mode in NetworkMode],
        default=NetworkMode.BLOCKED.value,
    )
    parser.add_argument("--cidr", action="append", default=[])
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--verbose", action="store_true")


def _cmd_doctor(args: argparse.Namespace, manager: SandboxManager) -> tuple[int, Any, str]:
    """Validate the local Modal environment without touching persisted state."""

    _ = (args, manager)
    report = validate_modal_environment()
    human = [
        f"modal installed: {report.modal_installed}",
        f"modal version: {report.modal_version or 'unknown'}",
        f"auth configured: {report.auth_configured}",
        f"config path: {report.modal_config_path or 'not found'}",
    ]
    if report.messages:
        human.append("messages:")
        human.extend(f"- {message}" for message in report.messages)
    if report.recommended_actions:
        human.append("recommended actions:")
        human.extend(f"- {message}" for message in report.recommended_actions)
    return (EXIT_OK if report.ok else EXIT_MODAL, report.model_dump(mode="json"), "\n".join(human))


def _cmd_session_start(args: argparse.Namespace, manager: SandboxManager) -> tuple[int, Any, str]:
    _ensure_modal_ready()
    record = manager.start_session(_build_config(args))
    return EXIT_OK, record.model_dump(mode="json"), _render_session(record)


def _cmd_session_attach(args: argparse.Namespace, manager: SandboxManager) -> tuple[int, Any, str]:
    _ensure_modal_ready()
    record = manager.attach_session(args.sandbox_id, _build_config(args))
    return EXIT_OK, record.model_dump(mode="json"), _render_session(record)


def _cmd_session_show(args: argparse.Namespace, manager: SandboxManager) -> tuple[int, Any, str]:
    record = manager.get_session(args.session_id)
    return EXIT_OK, record.model_dump(mode="json"), _render_session(record)


def _cmd_session_list(args: argparse.Namespace, manager: SandboxManager) -> tuple[int, Any, str]:
    _ = args
    records = manager.list_sessions()
    payload = [record.model_dump(mode="json") for record in records]
    human = (
        "\n\n".join(_render_session(record) for record in records)
        if records
        else "no stored sessions"
    )
    return EXIT_OK, payload, human


def _cmd_session_terminate(
    args: argparse.Namespace, manager: SandboxManager
) -> tuple[int, Any, str]:
    _ensure_modal_ready()
    record = manager.terminate_session(args.session_id)
    return EXIT_OK, record.model_dump(mode="json"), _render_session(record)


def _cmd_run_python(args: argparse.Namespace, manager: SandboxManager) -> tuple[int, Any, str]:
    _ensure_modal_ready()
    code = args.code if args.code is not None else Path(args.file).read_text(encoding="utf-8")
    result = manager.run_python(args.session_id, code, timeout_seconds=args.timeout_seconds)
    return _run_response(result)


def _cmd_run_shell(args: argparse.Namespace, manager: SandboxManager) -> tuple[int, Any, str]:
    _ensure_modal_ready()
    result = manager.run_shell(
        args.session_id, args.command_text, timeout_seconds=args.timeout_seconds
    )
    return _run_response(result)


def _cmd_run_show(args: argparse.Namespace, manager: SandboxManager) -> tuple[int, Any, str]:
    result = manager.get_run(args.run_id)
    return EXIT_OK, result.model_dump(mode="json"), _render_run(result)


def _cmd_run_list(args: argparse.Namespace, manager: SandboxManager) -> tuple[int, Any, str]:
    runs = manager.list_runs(session_id=args.session_id)
    payload = [run.model_dump(mode="json") for run in runs]
    human = "\n\n".join(_render_run(run) for run in runs) if runs else "no stored runs"
    return EXIT_OK, payload, human


def _cmd_artifact_list(args: argparse.Namespace, manager: SandboxManager) -> tuple[int, Any, str]:
    artifacts = manager.list_artifacts(args.run_id)
    payload = [artifact.model_dump(mode="json") for artifact in artifacts]
    if artifacts:
        human = "\n".join(
            f"- {artifact.path} [{artifact.change_type.value}] {artifact.size_bytes} bytes"
            for artifact in artifacts
        )
    else:
        human = "no artifacts recorded for this run"
    return EXIT_OK, payload, human


def _cmd_artifact_show(args: argparse.Namespace, manager: SandboxManager) -> tuple[int, Any, str]:
    _ensure_modal_ready()
    preview = manager.show_artifact(args.run_id, args.path, max_chars=args.max_chars)
    human = f"{preview.remote_path}\n\n{preview.preview}"
    if preview.truncated:
        human += "\n\n[preview truncated]"
    return EXIT_OK, preview.model_dump(mode="json"), human


def _cmd_artifact_download(
    args: argparse.Namespace, manager: SandboxManager
) -> tuple[int, Any, str]:
    _ensure_modal_ready()
    destination = manager.download_artifact(args.run_id, args.path, args.destination)
    payload = {"destination": str(destination)}
    human = f"downloaded to {destination!s}"
    return EXIT_OK, payload, human


def _cmd_serve(args: argparse.Namespace, manager: SandboxManager) -> tuple[int, Any, str]:
    """Start the optional HTTP service bound to the CLI-selected state directory."""

    try:
        import uvicorn

        server_app_module = importlib.import_module("agent_sandbox.server.app")
        server_settings_module = importlib.import_module("agent_sandbox.server.settings")
        create_app = server_app_module.create_app
        ServiceSettings = server_settings_module.ServiceSettings
    except ImportError as exc:  # pragma: no cover - exercised in real installs
        raise ConfigurationError(
            "The optional HTTP API requires the server extra. "
            "Install 'agent-sandbox-modal[server]'."
        ) from exc
    app = create_app(
        settings=ServiceSettings(state_dir=args.state_dir),
        manager=manager,
        store=manager.store,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return (
        EXIT_OK,
        {"host": args.host, "port": args.port},
        f"server stopped on http://{args.host}:{args.port}",
    )


def _run_response(result: ExecutionResult) -> tuple[int, Any, str]:
    """Map a run result to the CLI's exit-code and output contract."""

    exit_code = EXIT_OK if result.status is ExecutionStatus.SUCCEEDED else EXIT_RUN_FAILED
    return exit_code, result.model_dump(mode="json"), _render_run(result)


def _ensure_modal_ready() -> None:
    """Fail early when a command requires a usable local Modal environment."""

    validate_modal_environment(raise_on_error=True)


def _build_config(args: argparse.Namespace) -> ModalSandboxConfig:
    """Translate CLI flags into a validated ``ModalSandboxConfig``."""

    tags: dict[str, str] = {}
    for item in args.tag:
        if "=" not in item:
            raise ConfigurationError(f"Tags must be provided as key=value, got {item!r}.")
        key, value = item.split("=", 1)
        tags[key] = value

    if args.ephemeral_disk_mb is not None:
        raise ConfigurationError(
            "ephemeral_disk_mb is not currently supported by Modal Sandboxes "
            "under this package baseline."
        )

    return ModalSandboxConfig(
        app_name=args.app_name,
        python_version=args.python_version,
        python_packages=tuple(args.python_packages),
        timeout_seconds=args.timeout_seconds,
        idle_timeout_seconds=args.idle_timeout_seconds,
        default_exec_timeout_seconds=args.default_exec_timeout_seconds,
        working_dir=args.working_dir,
        shell_executable=args.shell_executable,
        max_output_chars=args.max_output_chars,
        max_value_repr_chars=args.max_value_repr_chars,
        artifact_max_preview_chars=args.artifact_max_preview_chars,
        capture_artifacts=args.capture_artifacts,
        cpu=args.cpu,
        memory_mb=args.memory_mb,
        ephemeral_disk_mb=args.ephemeral_disk_mb,
        network=NetworkPolicy(mode=NetworkMode(args.network), cidr_allowlist=tuple(args.cidr)),
        verbose=args.verbose,
        tags=tags,
    )


def _render_session(record: StoredSession) -> str:
    """Render one stored session in the CLI's human-readable format."""

    info = record.info
    lines = [
        f"session_id: {info.session_id}",
        f"sandbox_id: {info.sandbox_id or '-'}",
        f"status: {info.status.value}",
        f"run_count: {info.run_count}",
        f"app_name: {info.app_name}",
        f"working_dir: {info.working_dir}",
        f"updated_at: {info.updated_at.isoformat()}",
    ]
    if info.last_run_id:
        lines.append(f"last_run_id: {info.last_run_id}")
    return "\n".join(lines)


def _render_run(result: ExecutionResult) -> str:
    """Render one execution result in the CLI's human-readable format."""

    lines = [
        f"run_id: {result.run_id}",
        f"session_id: {result.session_id}",
        f"sandbox_id: {result.sandbox_id or '-'}",
        f"kind: {result.kind.value}",
        f"status: {result.status.value}",
        f"duration_seconds: {result.duration_seconds:.3f}",
        f"sequence_number: {result.sequence_number}",
    ]
    if result.command:
        lines.append(f"command: {' '.join(result.command)}")
    if result.value_repr is not None:
        lines.append(f"value_repr: {result.value_repr}")
    if result.error_type or result.error_message:
        lines.append(f"error: {result.error_type or '-'}: {result.error_message or '-'}")
    if result.stdout:
        lines.append("stdout:")
        lines.append(result.stdout.rstrip())
    if result.stderr:
        lines.append("stderr:")
        lines.append(result.stderr.rstrip())
    if result.artifacts:
        lines.append("artifacts:")
        lines.extend(
            f"- {artifact.path} [{artifact.change_type.value}] {artifact.size_bytes} bytes"
            for artifact in result.artifacts
        )
    return "\n".join(lines)


def _emit(*, payload: Any, human: str, json_mode: bool) -> None:
    """Emit either JSON or human-readable output to stdout."""

    if json_mode:
        sys.stdout.write(json.dumps(payload, indent=2))
        sys.stdout.write("\n")
        return
    sys.stdout.write(human.rstrip() + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a stable process exit code.

    Usage errors, configuration failures, missing state, backend failures, and
    lifecycle violations each map to distinct exit codes so scripts can react
    without parsing stderr.
    """

    parser = build_parser()
    raw_argv = list(argv) if argv is not None else list(sys.argv[1:])
    json_requested = "--json" in raw_argv

    try:
        args = parser.parse_args(raw_argv)
    except UsageError as exc:
        _emit(
            payload={
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "usage": parser.format_usage().strip(),
            },
            human=f"usage error: {exc}",
            json_mode=json_requested,
        )
        return EXIT_USAGE
    except SystemExit as exc:
        if exc.code in (0, None):
            return 0
        _emit(
            payload={
                "error": {
                    "type": "UsageError",
                    "message": "Invalid command line usage.",
                },
                "usage": parser.format_usage().strip(),
            },
            human="usage error: Invalid command line usage.",
            json_mode=json_requested,
        )
        return EXIT_USAGE

    configure_basic_logging(level=args.log_level)
    manager = SandboxManager(LocalStateStore(args.state_dir))

    try:
        exit_code, payload, human = args.func(args, manager)
        _emit(payload=payload, human=human, json_mode=args.json_mode)
        return exit_code
    except ModalConfigurationError as exc:
        _emit(
            payload={"error": {"type": type(exc).__name__, "message": str(exc)}},
            human=f"error: {exc}",
            json_mode=args.json_mode,
        )
        return EXIT_MODAL
    except (ValidationError, ConfigurationError) as exc:
        _emit(
            payload={"error": {"type": type(exc).__name__, "message": str(exc)}},
            human=f"error: {exc}",
            json_mode=args.json_mode,
        )
        return EXIT_CONFIG
    except (SessionNotFoundError, RunNotFoundError, ArtifactNotFoundError) as exc:
        _emit(
            payload={"error": {"type": type(exc).__name__, "message": str(exc)}},
            human=f"error: {exc}",
            json_mode=args.json_mode,
        )
        return EXIT_NOT_FOUND
    except BackendError as exc:
        _emit(
            payload={"error": {"type": type(exc).__name__, "message": str(exc)}},
            human=f"error: {exc}",
            json_mode=args.json_mode,
        )
        return EXIT_BACKEND
    except SessionError as exc:
        _emit(
            payload={"error": {"type": type(exc).__name__, "message": str(exc)}},
            human=f"error: {exc}",
            json_mode=args.json_mode,
        )
        return EXIT_LIFECYCLE
    except AgentSandboxError as exc:
        _emit(
            payload={"error": {"type": type(exc).__name__, "message": str(exc)}},
            human=f"error: {exc}",
            json_mode=args.json_mode,
        )
        return EXIT_INTERNAL
    except Exception as exc:  # pragma: no cover - defensive fallback
        _emit(
            payload={"error": {"type": type(exc).__name__, "message": str(exc)}},
            human=f"error: {exc}",
            json_mode=args.json_mode,
        )
        return EXIT_INTERNAL


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
