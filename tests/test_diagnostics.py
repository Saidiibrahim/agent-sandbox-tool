"""Diagnostics tests for Modal install, auth, and config-file detection."""

from __future__ import annotations

import importlib

import pytest

from agent_sandbox.diagnostics import validate_modal_environment
from agent_sandbox.exceptions import ModalConfigurationError


def test_validate_modal_environment_reports_missing_modal(monkeypatch, tmp_path) -> None:
    def fake_import_module(name: str):
        if name == "modal":
            raise ImportError("missing modal")
        return importlib.import_module(name)

    monkeypatch.setattr("agent_sandbox.diagnostics.importlib.import_module", fake_import_module)
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    monkeypatch.setenv("MODAL_CONFIG_PATH", str(tmp_path / "missing-modal.toml"))

    report = validate_modal_environment()

    assert report.ok is False
    assert report.modal_installed is False
    assert report.auth_configured is False
    assert report.messages


def test_validate_modal_environment_rejects_empty_modal_config(monkeypatch, tmp_path) -> None:
    def fake_import_module(name: str):
        if name == "modal":

            class DummyModal:
                __name__ = "modal"

            return DummyModal()
        return importlib.import_module(name)

    config_path = tmp_path / "empty-modal.toml"
    config_path.write_text("", encoding="utf-8")

    monkeypatch.setattr("agent_sandbox.diagnostics.importlib.import_module", fake_import_module)
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    monkeypatch.setenv("MODAL_CONFIG_PATH", str(config_path))

    report = validate_modal_environment()

    assert report.ok is False
    assert report.auth_configured is False
    assert report.modal_config_path == str(config_path)
    assert any("empty" in message.lower() for message in report.messages)


def test_validate_modal_environment_rejects_invalid_modal_config(monkeypatch, tmp_path) -> None:
    def fake_import_module(name: str):
        if name == "modal":

            class DummyModal:
                __name__ = "modal"

            return DummyModal()
        return importlib.import_module(name)

    config_path = tmp_path / "invalid-modal.toml"
    config_path.write_text("[profiles", encoding="utf-8")

    monkeypatch.setattr("agent_sandbox.diagnostics.importlib.import_module", fake_import_module)
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    monkeypatch.setenv("MODAL_CONFIG_PATH", str(config_path))

    report = validate_modal_environment()

    assert report.ok is False
    assert report.auth_configured is False
    assert report.modal_config_path == str(config_path)
    assert any("invalid toml" in message.lower() for message in report.messages)
    with pytest.raises(ModalConfigurationError):
        validate_modal_environment(raise_on_error=True)


def test_validate_modal_environment_accepts_env_tokens(monkeypatch) -> None:
    monkeypatch.setenv("MODAL_TOKEN_ID", "id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "secret")

    report = validate_modal_environment()

    assert report.auth_configured is True
