"""Optional FastAPI transport for managed sandbox sessions.

The HTTP service stays intentionally thin: it delegates lifecycle and run work
to ``SandboxManager``, preserves the same domain exceptions, and maps those
exceptions into explicit HTTP status codes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

try:  # pragma: no cover - exercised in real installs
    from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
    from fastapi.responses import JSONResponse
except ImportError as exc:  # pragma: no cover - exercised in real installs
    raise ImportError(
        "The optional HTTP API requires the server extra. Install 'agent-sandbox-modal[server]'."
    ) from exc

from ..config import ModalSandboxConfig
from ..exceptions import (
    AgentSandboxError,
    ArtifactNotFoundError,
    BackendError,
    ConfigurationError,
    ModalConfigurationError,
    RunNotFoundError,
    SessionError,
    SessionNotFoundError,
)
from ..manager import SandboxManager
from ..models import ArtifactMetadata, ArtifactPreview, ExecutionResult, SessionInfo
from ..state import LocalStateStore
from .settings import ServiceSettings


class CreateSessionRequest(BaseModel):
    """Request body for creating a fresh managed session."""

    model_config = ConfigDict(extra="forbid")

    config: ModalSandboxConfig


class AttachSessionRequest(BaseModel):
    """Request body for registering an existing sandbox ID."""

    model_config = ConfigDict(extra="forbid")

    sandbox_id: str
    config: ModalSandboxConfig


class PythonRunRequest(BaseModel):
    """Request body for one managed Python execution."""

    model_config = ConfigDict(extra="forbid")

    code: str
    timeout_seconds: int | None = Field(default=None, ge=1)


class ShellRunRequest(BaseModel):
    """Request body for one managed shell execution."""

    model_config = ConfigDict(extra="forbid")

    command: str
    timeout_seconds: int | None = Field(default=None, ge=1)


class SessionResponse(BaseModel):
    """Serialized managed session record returned by the API."""

    model_config = ConfigDict(extra="forbid")

    info: SessionInfo
    config: ModalSandboxConfig


class RunsResponse(BaseModel):
    """Collection wrapper for recorded runs."""

    model_config = ConfigDict(extra="forbid")

    runs: list[ExecutionResult]


class ArtifactsResponse(BaseModel):
    """Collection wrapper for recorded artifact metadata."""

    model_config = ConfigDict(extra="forbid")

    artifacts: list[ArtifactMetadata]


def _json_error(status_code: int, exc: Exception) -> JSONResponse:
    """Render domain exceptions into the API's stable JSON error envelope."""

    return JSONResponse(
        status_code=status_code,
        content={"error": {"type": type(exc).__name__, "message": str(exc)}},
    )


def create_app(
    settings: ServiceSettings | None = None,
    *,
    manager: SandboxManager | None = None,
    store: LocalStateStore | None = None,
) -> FastAPI:
    """Create a FastAPI app bound to a state store and manager.

    Callers may inject a prebuilt manager or store for tests and embedding. If
    they do not, the app constructs them at startup from ``ServiceSettings``.
    """

    service_settings = settings or ServiceSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_store = store or LocalStateStore(service_settings.state_dir)
        resolved_manager = manager or SandboxManager(resolved_store)
        app.state.settings = service_settings
        app.state.store = resolved_store
        app.state.manager = resolved_manager
        yield

    app = FastAPI(title=service_settings.title, lifespan=lifespan)

    @app.exception_handler(SessionNotFoundError)
    async def handle_session_not_found(request: Request, exc: SessionNotFoundError) -> JSONResponse:
        _ = request
        return _json_error(status.HTTP_404_NOT_FOUND, exc)

    @app.exception_handler(RunNotFoundError)
    async def handle_run_not_found(request: Request, exc: RunNotFoundError) -> JSONResponse:
        _ = request
        return _json_error(status.HTTP_404_NOT_FOUND, exc)

    @app.exception_handler(ArtifactNotFoundError)
    async def handle_artifact_not_found(
        request: Request, exc: ArtifactNotFoundError
    ) -> JSONResponse:
        _ = request
        return _json_error(status.HTTP_404_NOT_FOUND, exc)

    @app.exception_handler(ConfigurationError)
    async def handle_configuration_error(request: Request, exc: ConfigurationError) -> JSONResponse:
        _ = request
        return _json_error(status.HTTP_400_BAD_REQUEST, exc)

    @app.exception_handler(ModalConfigurationError)
    async def handle_modal_configuration_error(
        request: Request, exc: ModalConfigurationError
    ) -> JSONResponse:
        _ = request
        return _json_error(status.HTTP_503_SERVICE_UNAVAILABLE, exc)

    @app.exception_handler(SessionError)
    async def handle_session_error(request: Request, exc: SessionError) -> JSONResponse:
        _ = request
        return _json_error(status.HTTP_409_CONFLICT, exc)

    @app.exception_handler(BackendError)
    async def handle_backend_error(request: Request, exc: BackendError) -> JSONResponse:
        _ = request
        return _json_error(status.HTTP_502_BAD_GATEWAY, exc)

    @app.exception_handler(AgentSandboxError)
    async def handle_agent_sandbox_error(request: Request, exc: AgentSandboxError) -> JSONResponse:
        _ = request
        return _json_error(status.HTTP_500_INTERNAL_SERVER_ERROR, exc)

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid4().hex
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    def get_manager(request: Request) -> SandboxManager:
        manager_instance: SandboxManager = request.app.state.manager
        return manager_instance

    def require_auth(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        settings_value: ServiceSettings = request.app.state.settings
        token = settings_value.bearer_token
        if token is None:
            return None
        if authorization != f"Bearer {token}":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
        return None

    # Keep the dependency object concrete inside the app factory. FastAPI can
    # otherwise misread postponed annotations here as query parameters.
    manager_dependency = Depends(get_manager)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/sessions", response_model=SessionResponse, dependencies=[Depends(require_auth)])
    def create_session(
        payload: CreateSessionRequest,
        manager: SandboxManager = manager_dependency,
    ) -> SessionResponse:
        record = manager.start_session(payload.config)
        return SessionResponse(info=record.info, config=record.config)

    @app.post(
        "/sessions/attach", response_model=SessionResponse, dependencies=[Depends(require_auth)]
    )
    def attach_session(
        payload: AttachSessionRequest,
        manager: SandboxManager = manager_dependency,
    ) -> SessionResponse:
        record = manager.attach_session(payload.sandbox_id, payload.config)
        return SessionResponse(info=record.info, config=record.config)

    @app.get(
        "/sessions", response_model=list[SessionResponse], dependencies=[Depends(require_auth)]
    )
    def list_sessions(manager: SandboxManager = manager_dependency) -> list[SessionResponse]:
        return [
            SessionResponse(info=record.info, config=record.config)
            for record in manager.list_sessions()
        ]

    @app.get(
        "/sessions/{session_id}",
        response_model=SessionResponse,
        dependencies=[Depends(require_auth)],
    )
    def get_session(
        session_id: str,
        manager: SandboxManager = manager_dependency,
    ) -> SessionResponse:
        record = manager.get_session(session_id)
        return SessionResponse(info=record.info, config=record.config)

    @app.post(
        "/sessions/{session_id}/runs/python",
        response_model=ExecutionResult,
        dependencies=[Depends(require_auth)],
    )
    def run_python(
        session_id: str,
        payload: PythonRunRequest,
        manager: SandboxManager = manager_dependency,
    ) -> ExecutionResult:
        return manager.run_python(session_id, payload.code, timeout_seconds=payload.timeout_seconds)

    @app.post(
        "/sessions/{session_id}/runs/shell",
        response_model=ExecutionResult,
        dependencies=[Depends(require_auth)],
    )
    def run_shell(
        session_id: str,
        payload: ShellRunRequest,
        manager: SandboxManager = manager_dependency,
    ) -> ExecutionResult:
        return manager.run_shell(
            session_id, payload.command, timeout_seconds=payload.timeout_seconds
        )

    @app.post(
        "/sessions/{session_id}/terminate",
        response_model=SessionResponse,
        dependencies=[Depends(require_auth)],
    )
    def terminate_session(
        session_id: str,
        manager: SandboxManager = manager_dependency,
    ) -> SessionResponse:
        record = manager.terminate_session(session_id)
        return SessionResponse(info=record.info, config=record.config)

    @app.get("/runs", response_model=RunsResponse, dependencies=[Depends(require_auth)])
    def list_runs(
        manager: SandboxManager = manager_dependency,
        session_id: str | None = None,
    ) -> RunsResponse:
        return RunsResponse(runs=manager.list_runs(session_id=session_id))

    @app.get("/runs/{run_id}", response_model=ExecutionResult, dependencies=[Depends(require_auth)])
    def get_run(
        run_id: str,
        manager: SandboxManager = manager_dependency,
    ) -> ExecutionResult:
        return manager.get_run(run_id)

    @app.get(
        "/runs/{run_id}/artifacts",
        response_model=ArtifactsResponse,
        dependencies=[Depends(require_auth)],
    )
    def list_artifacts(
        run_id: str,
        manager: SandboxManager = manager_dependency,
    ) -> ArtifactsResponse:
        return ArtifactsResponse(artifacts=list(manager.list_artifacts(run_id)))

    @app.get(
        "/runs/{run_id}/artifacts/preview",
        response_model=ArtifactPreview,
        dependencies=[Depends(require_auth)],
    )
    def show_artifact(
        run_id: str,
        path: str,
        manager: SandboxManager = manager_dependency,
        max_chars: int | None = None,
    ) -> ArtifactPreview:
        return manager.show_artifact(run_id, path, max_chars=max_chars)

    return app


def create_default_app() -> FastAPI:
    """Create the default app instance used by ASGI servers."""

    return create_app(ServiceSettings())
