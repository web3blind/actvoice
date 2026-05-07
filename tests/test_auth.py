from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.auth import AgentAuthStore, AgentRegistrationRequest
from app.store import ProjectStore


def test_agent_auth_store_register_and_verify(tmp_path, monkeypatch):
    monkeypatch.setenv("ACTVOICE_REGISTRATION_CODE", "invite")
    auth = AgentAuthStore(tmp_path / "agents.json")

    with pytest.raises(PermissionError):
        auth.register(AgentRegistrationRequest(agent_name="bad", registration_code="wrong"))

    response = auth.register(AgentRegistrationRequest(agent_name="Hermes", registration_code="invite"))
    assert response.api_key.startswith("av_")
    assert auth.verify(response.api_key)
    assert not auth.verify("av_invalid")


def test_write_endpoints_require_bearer_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ACTVOICE_REGISTRATION_CODE", raising=False)
    main.store = ProjectStore(tmp_path / "projects")
    main.render_service.store = main.store
    main.auth_store = AgentAuthStore(tmp_path / "agents.json")
    client = TestClient(main.app)

    unauth = client.post("/api/projects", json={"title": "Nope", "language": "ru"})
    assert unauth.status_code == 401

    reg = client.post("/api/agents/register", json={"agent_name": "Hermes", "purpose": "test"})
    assert reg.status_code == 200
    api_key = reg.json()["api_key"]

    ok = client.post(
        "/api/projects",
        json={"title": "Allowed", "language": "ru"},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert ok.status_code == 200
    assert ok.json()["title"] == "Allowed"
