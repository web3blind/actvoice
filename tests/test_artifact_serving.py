from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main
from app.auth import AgentAuthStore
from app.models import Artifact
from app.render_queue import RenderQueue
from app.store import ProjectStore


def test_artifact_metadata_includes_download_url_and_mp3_endpoint_serves_file(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    project = store.create_project("Artifact", "ru")
    build = store.project_dir(project.id) / "build"
    build.mkdir(parents=True)
    mp3 = build / "final_mix.mp3"
    mp3.write_bytes(b"ID3fake mp3 bytes")
    project.artifact = Artifact(
        mp3_path=str(mp3),
        duration_sec=1.23,
        mp3_url=f"/api/projects/{project.id}/artifact.mp3",
    )
    store.save(project)

    main.store = store
    main.auth_store = AgentAuthStore(tmp_path / "agents.json")
    main.render_queue = RenderQueue(store, render_service=main.render_service, max_workers=1)
    client = TestClient(main.app)

    metadata = client.get(f"/api/projects/{project.id}/artifact")
    assert metadata.status_code == 200
    assert metadata.json()["mp3_url"] == f"/api/projects/{project.id}/artifact.mp3"

    download = client.get(f"/api/projects/{project.id}/artifact.mp3")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("audio/mpeg")
    assert download.content == b"ID3fake mp3 bytes"


def test_artifact_mp3_endpoint_rejects_unrendered_project(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    project = store.create_project("No artifact", "ru")
    main.store = store
    client = TestClient(main.app)

    response = client.get(f"/api/projects/{project.id}/artifact.mp3")

    assert response.status_code == 404
