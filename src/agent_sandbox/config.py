"""Typed configuration models for Modal-backed sandbox sessions.

These models validate security-sensitive defaults, timeout relationships, and
resource knobs before the backend talks to Modal so callers get consistent
errors across the library, CLI, and HTTP service.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NetworkMode(StrEnum):
    """Outbound networking policy for the sandbox."""

    BLOCKED = "blocked"
    ALLOW_ALL = "allow_all"
    ALLOWLIST = "allowlist"


class NetworkPolicy(BaseModel):
    """Outbound network policy translated into Modal sandbox create options.

    The default remains deny-by-default. Allowlists are explicit and must carry
    concrete CIDR entries so configuration does not silently overexpose egress.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: NetworkMode = NetworkMode.BLOCKED
    cidr_allowlist: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("cidr_allowlist")
    @classmethod
    def _strip_cidrs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(item.strip() for item in value if item.strip())

    @model_validator(mode="after")
    def _validate_allowlist_usage(self) -> NetworkPolicy:
        if self.mode is NetworkMode.ALLOWLIST and not self.cidr_allowlist:
            raise ValueError("cidr_allowlist must be non-empty when mode='allowlist'.")
        if self.mode is not NetworkMode.ALLOWLIST and self.cidr_allowlist:
            raise ValueError("cidr_allowlist may only be set when mode='allowlist'.")
        return self


class ModalSandboxConfig(BaseModel):
    """Public configuration for a Modal-backed sandbox session.

    The library is Modal-specific, so the config intentionally includes Modal-facing
    concerns like image customization and Secrets. Those fields are kept optional so
    the default path stays lightweight. Validation also rejects resource settings
    that this package baseline cannot actually honor, such as ephemeral disk.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    app_name: str = Field(default="agent-sandbox")
    python_version: str = Field(default="3.11")
    python_packages: tuple[str, ...] = Field(default_factory=tuple)
    timeout_seconds: int = Field(default=30 * 60, ge=1, le=24 * 60 * 60)
    idle_timeout_seconds: int | None = Field(default=5 * 60, ge=1)
    default_exec_timeout_seconds: int = Field(default=120, ge=1)
    working_dir: str = Field(default="/workspace")
    shell_executable: str = Field(default="/bin/bash")
    max_output_chars: int = Field(default=50_000, ge=512)
    max_value_repr_chars: int = Field(default=10_000, ge=128)
    artifact_max_preview_chars: int = Field(default=10_000, ge=256)
    capture_artifacts: bool = Field(default=True)
    cpu: float | None = Field(default=None, gt=0)
    memory_mb: int | None = Field(default=None, gt=0)
    ephemeral_disk_mb: int | None = Field(default=None, gt=0)
    network: NetworkPolicy = Field(default_factory=NetworkPolicy)
    verbose: bool = Field(default=False)
    image: Any | None = Field(default=None, exclude=True, repr=False)
    secrets: tuple[Any, ...] = Field(default_factory=tuple, exclude=True, repr=False)
    tags: dict[str, str] = Field(default_factory=dict)

    @field_validator("app_name")
    @classmethod
    def _validate_app_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("app_name must not be empty.")
        return cleaned

    @field_validator("python_version")
    @classmethod
    def _validate_python_version(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("python_version must not be empty.")
        return cleaned

    @field_validator("python_packages")
    @classmethod
    def _normalize_packages(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(pkg.strip() for pkg in value if pkg.strip())

    @field_validator("working_dir")
    @classmethod
    def _normalize_working_dir(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.startswith("/"):
            raise ValueError("working_dir must be an absolute path inside the sandbox.")
        return cleaned.rstrip("/") or "/"

    @field_validator("shell_executable")
    @classmethod
    def _normalize_shell_executable(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("shell_executable must not be empty.")
        return cleaned

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: dict[str, str]) -> dict[str, str]:
        return {
            str(key).strip(): str(val).strip() for key, val in value.items() if str(key).strip()
        }

    @model_validator(mode="after")
    def _validate_timeout_relationships(self) -> ModalSandboxConfig:
        """Reject timeout and resource combinations that would misstate runtime behavior."""
        if self.default_exec_timeout_seconds > self.timeout_seconds:
            raise ValueError(
                "default_exec_timeout_seconds cannot exceed timeout_seconds for the sandbox."
            )
        if self.ephemeral_disk_mb is not None:
            raise ValueError(
                "ephemeral_disk_mb is not currently supported by Modal Sandboxes "
                "under this package baseline."
            )
        return self
