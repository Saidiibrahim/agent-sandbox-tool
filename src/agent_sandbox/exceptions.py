"""Package-specific exception hierarchy."""

from __future__ import annotations


class AgentSandboxError(Exception):
    """Base exception for the package."""


class ConfigurationError(AgentSandboxError):
    """Raised for invalid library configuration."""


class SessionError(AgentSandboxError):
    """Raised for invalid session lifecycle usage."""


class SessionClosedError(SessionError):
    """Raised when a closed session is used."""


class SessionDetachedError(SessionError):
    """Raised when a detached session is used without re-attaching."""


class BackendError(AgentSandboxError):
    """Raised when the Modal backend fails to perform an operation."""


class SandboxStartupError(BackendError):
    """Raised when a sandbox cannot be created or attached."""


class ExecutionError(AgentSandboxError):
    """Raised when the library cannot produce a trustworthy execution result."""


class ExecutionTimeoutError(ExecutionError):
    """Raised when a timeout needs to be represented as an exception."""


class ProtocolError(ExecutionError):
    """Raised when the Python execution protocol returns malformed data."""
