"""Package-specific exception hierarchy.

The library intentionally keeps lifecycle, configuration, protocol, artifact,
and persistence failures distinct so the CLI and HTTP service can map them to
stable exit codes and HTTP responses without parsing error strings.
"""

from __future__ import annotations


class AgentSandboxError(Exception):
    """Base exception for the package."""


class ConfigurationError(AgentSandboxError):
    """Raised for invalid library or operator-supplied configuration."""


class ModalConfigurationError(ConfigurationError):
    """Raised when Modal is missing or unusable in the current environment."""


class SessionError(AgentSandboxError):
    """Raised for invalid session lifecycle usage."""


class SessionClosedError(SessionError):
    """Raised when a closed session is used."""


class SessionDetachedError(SessionError):
    """Raised when a detached session is reused instead of re-attached."""


class BackendError(AgentSandboxError):
    """Raised when the backend cannot complete a sandbox operation."""


class SandboxStartupError(BackendError):
    """Raised when a sandbox cannot be created or attached."""


class ExecutionError(AgentSandboxError):
    """Raised when the library cannot produce a trustworthy execution result."""


class ExecutionTimeoutError(ExecutionError):
    """Raised when timeout semantics must be surfaced as an exception."""


class ProtocolError(ExecutionError):
    """Raised when the Python execution protocol returns malformed data."""


class ArtifactError(AgentSandboxError):
    """Raised when artifact metadata or file retrieval fails."""


class ArtifactNotFoundError(ArtifactError):
    """Raised when an expected artifact cannot be found."""


class StateStoreError(AgentSandboxError):
    """Raised when persisted CLI/session state cannot be read or written safely."""


class SessionNotFoundError(StateStoreError):
    """Raised when a stored session record cannot be found."""


class RunNotFoundError(StateStoreError):
    """Raised when a stored run record cannot be found."""
