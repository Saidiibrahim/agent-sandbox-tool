"""Public package surface for the Modal-backed agent sandbox library.

The package re-exports the stable configuration, session, tool, state, and
operator-facing types so embedding applications can import from
``agent_sandbox`` without depending on the internal module layout.
"""

from .config import ModalSandboxConfig, NetworkMode, NetworkPolicy
from .diagnostics import ModalEnvironmentReport, validate_modal_environment
from .exceptions import (
    AgentSandboxError,
    ArtifactError,
    ArtifactNotFoundError,
    BackendError,
    ConfigurationError,
    ExecutionError,
    ExecutionTimeoutError,
    ModalConfigurationError,
    ProtocolError,
    RunNotFoundError,
    SandboxStartupError,
    SessionClosedError,
    SessionDetachedError,
    SessionError,
    SessionNotFoundError,
    StateStoreError,
)
from .manager import SandboxManager
from .models import (
    ArtifactChangeType,
    ArtifactMetadata,
    ArtifactPreview,
    ExecutionKind,
    ExecutionResult,
    ExecutionStatus,
    SandboxHandle,
    SessionInfo,
    SessionStatus,
)
from .session import AsyncSandboxSession, SandboxSession
from .state import LocalStateStore, StoredSession
from .tool import AsyncPythonSandboxTool, AsyncShellSandboxTool, PythonSandboxTool, ShellSandboxTool

__all__ = [
    "AgentSandboxError",
    "ArtifactChangeType",
    "ArtifactError",
    "ArtifactMetadata",
    "ArtifactNotFoundError",
    "ArtifactPreview",
    "AsyncPythonSandboxTool",
    "AsyncSandboxSession",
    "AsyncShellSandboxTool",
    "BackendError",
    "ConfigurationError",
    "ExecutionError",
    "ExecutionKind",
    "ExecutionResult",
    "ExecutionStatus",
    "ExecutionTimeoutError",
    "LocalStateStore",
    "ModalConfigurationError",
    "ModalEnvironmentReport",
    "ModalSandboxConfig",
    "NetworkMode",
    "NetworkPolicy",
    "ProtocolError",
    "PythonSandboxTool",
    "RunNotFoundError",
    "SandboxHandle",
    "SandboxManager",
    "SandboxSession",
    "SandboxStartupError",
    "SessionClosedError",
    "SessionDetachedError",
    "SessionError",
    "SessionInfo",
    "SessionNotFoundError",
    "SessionStatus",
    "ShellSandboxTool",
    "StateStoreError",
    "StoredSession",
    "validate_modal_environment",
]

__version__ = "0.2.0"
