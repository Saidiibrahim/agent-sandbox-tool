"""Environment-backed settings for the optional FastAPI service."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    """Runtime settings for the optional HTTP service.

    These settings stay intentionally small so deployments can wire a persisted
    state directory and optional bearer token without leaking broader library
    configuration into process-global environment variables.
    """

    title: str = "Agent Sandbox Modal API"
    state_dir: str | None = None
    bearer_token: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="AGENT_SANDBOX_API_",
        extra="ignore",
    )
