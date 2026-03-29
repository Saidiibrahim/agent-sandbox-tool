"""Diagnostics for confirming whether Modal is usable on the current machine.

The CLI and service startup paths use this module to distinguish package
installation problems from missing credentials or malformed local config.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .exceptions import ModalConfigurationError


class ModalEnvironmentReport(BaseModel):
    """Structured summary of whether Modal can be used right now."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    modal_installed: bool
    modal_version: str | None = None
    auth_configured: bool
    modal_config_path: str | None = None
    messages: tuple[str, ...] = Field(default_factory=tuple)
    recommended_actions: tuple[str, ...] = Field(default_factory=tuple)


def _inspect_config_file(config_path: Path) -> tuple[bool, str | None]:
    """Inspect a Modal config file for at least one usable credential profile."""

    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"Unable to read the Modal config file at {config_path!s}: {exc}"

    if not raw.strip():
        return False, f"Modal config file at {config_path!s} is empty."

    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        return False, f"Modal config file at {config_path!s} is invalid TOML: {exc}"

    if not isinstance(data, dict) or not data:
        return False, f"Modal config file at {config_path!s} does not contain any profiles."

    for _profile_name, profile in data.items():
        if not isinstance(profile, dict):
            continue
        token_id = profile.get("token_id")
        token_secret = profile.get("token_secret")
        if token_id and token_secret:
            return True, None

    return (
        False,
        "Modal config file at "
        f"{config_path!s} does not contain usable token_id/token_secret credentials.",
    )


def validate_modal_environment(*, raise_on_error: bool = False) -> ModalEnvironmentReport:
    """Return a best-effort report about local Modal install and auth readiness.

    Environment variables take precedence over file-based credentials. When
    ``raise_on_error`` is true, the aggregated findings are promoted to
    ``ModalConfigurationError`` so operator surfaces can fail early.
    """

    messages: list[str] = []
    actions: list[str] = []
    config_issue: str | None = None

    try:
        importlib.import_module("modal")
        modal_installed = True
        try:
            modal_version = importlib.metadata.version("modal")
        except importlib.metadata.PackageNotFoundError:
            modal_version = None
    except ImportError:
        modal_installed = False
        modal_version = None
        messages.append("The 'modal' package is not installed in this Python environment.")
        actions.append("Install the project dependencies so the 'modal' package is available.")
    except Exception as exc:
        modal_installed = True
        try:
            modal_version = importlib.metadata.version("modal")
        except importlib.metadata.PackageNotFoundError:
            modal_version = None
        messages.append(f"Modal could not be initialized cleanly: {exc}")
        actions.append("Fix the Modal config file and try again.")

    has_env_token = bool(os.getenv("MODAL_TOKEN_ID") and os.getenv("MODAL_TOKEN_SECRET"))
    config_path = Path(os.getenv("MODAL_CONFIG_PATH", "~/.modal.toml")).expanduser()
    has_config_file = config_path.exists()
    has_config_token = False
    if has_config_file:
        has_config_token, config_issue = _inspect_config_file(config_path)
        if config_issue is not None:
            messages.append(config_issue)
            actions.append("Replace or regenerate the Modal config file.")

    auth_configured = has_env_token or has_config_token
    if not auth_configured:
        messages.append(
            "Modal credentials were not found in MODAL_TOKEN_ID/MODAL_TOKEN_SECRET "
            "or the configured modal config file."
        )
        actions.extend(
            [
                "Run 'modal setup' on this machine, or",
                "Run 'modal token set' and persist the credentials, or",
                "Set MODAL_TOKEN_ID and MODAL_TOKEN_SECRET in the environment.",
            ]
        )

    if modal_installed and auth_configured:
        messages.append("Modal appears to be installed and credentials are discoverable.")

    report = ModalEnvironmentReport(
        ok=modal_installed and auth_configured,
        modal_installed=modal_installed,
        modal_version=modal_version,
        auth_configured=auth_configured,
        modal_config_path=str(config_path) if has_config_file else None,
        messages=tuple(messages),
        recommended_actions=tuple(actions),
    )
    if raise_on_error and not report.ok:
        raise ModalConfigurationError(" ".join(messages + actions).strip())
    return report
