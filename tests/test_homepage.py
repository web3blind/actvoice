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
    assert "1. Register an agent" in html
    assert "2. Connect with MCP" in html
    assert "Authorization: Bearer" in html
    assert "actvoice.xyz/mcp" in html
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
