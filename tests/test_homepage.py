from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main


def test_homepage_contains_accessible_agent_instructions():
    client = TestClient(main.app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "ActVoice" in html
    assert "Audio drama studio for humans and AI agents" in html
    assert "Screen-reader friendly workflow" in html
    assert "Register an agent" in html
    assert "Connect with MCP" in html
    assert "1. Register an agent" not in html
    assert "2. Connect with MCP" not in html
    assert "Copy-ready examples" in html
    assert "data-copy-target=\"snippet-register-en\"" in html
    assert "curl -X POST https://actvoice.xyz/api/agents/register" in html
    assert "curl -L -o final_mix.mp3" in html
    assert "Copied to clipboard" in html
    assert "Authorization: Bearer [API_KEY]" in html
    assert "Bearer ***" not in html
    assert "ACTVOICE_API_KEY='[API_KEY]'" in html
    assert "actvoice.xyz/mcp" in html
    assert "data-language-panel=\"ru\"" in html
    assert "data-set-language=\"ru\"" in html
    assert "navigator.language" in html
    assert "localStorage.getItem('actvoice-language')" in html
    assert "Студия аудиоспектаклей для людей и AI-агентов" in html
    assert "Удобный workflow для скринридера" in html
    assert "Готовые примеры для копирования" in html
    assert "Скопировано в буфер обмена" in html
    assert "No visual timeline required" in html
    assert "timing anchors" in html
    assert "after_line" in html
    assert "no AI runs inside the core service" in html
    assert "REST rendering is queued" in html
    assert "edge" in html
    assert "local/offline fallback" in html
    assert "Author on X" in html
    assert "https://x.com/denis_skripnik" in html
    assert "Source on GitHub" in html
    assert "https://github.com/web3blind/actvoice" in html
    assert "artifact.mp3" in html
    assert "render-manifest.json" in html
