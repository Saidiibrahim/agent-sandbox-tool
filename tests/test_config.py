"""Configuration validation tests for security defaults and resource guards."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_sandbox.config import ModalSandboxConfig, NetworkMode, NetworkPolicy


def test_default_config_is_secure_by_default() -> None:
    config = ModalSandboxConfig()
    assert config.network.mode is NetworkMode.BLOCKED
    assert config.working_dir == "/workspace"
    assert config.default_exec_timeout_seconds == 120


def test_allowlist_requires_entries() -> None:
    with pytest.raises(ValidationError):
        NetworkPolicy(mode=NetworkMode.ALLOWLIST)


def test_non_allowlist_mode_rejects_cidrs() -> None:
    with pytest.raises(ValidationError):
        NetworkPolicy(mode=NetworkMode.BLOCKED, cidr_allowlist=("1.1.1.1/32",))


def test_exec_timeout_cannot_exceed_sandbox_timeout() -> None:
    with pytest.raises(ValidationError):
        ModalSandboxConfig(timeout_seconds=30, default_exec_timeout_seconds=31)


def test_ephemeral_disk_is_rejected_until_supported() -> None:
    with pytest.raises(ValidationError):
        ModalSandboxConfig(ephemeral_disk_mb=512)
