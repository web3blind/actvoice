from __future__ import annotations

from pathlib import Path

import pytest

from app.auth import AgentAuthStore, AgentRegistrationRequest
from app.models import Character, DialogueLine, Scene, SoundCue
from app.store import ProjectNotFound, ProjectStore


def test_project_store_persists_projects_in_sqlite(tmp_path):
    db_path = tmp_path / "actvoice.sqlite3"
    projects_dir = tmp_path / "projects"

    store = ProjectStore(projects_dir, db_path=db_path)
    project = store.create_project("SQLite Demo", "ru")
    character = Character(name="Narrator", voice="aleksandr")
    project = store.add_character(project.id, character)
    scene = Scene(title="Intro")
    project = store.add_scene(project.id, scene)
    project = store.add_line(project.id, scene.id, DialogueLine(speaker_id=character.id, text="Привет из SQLite."))
    store.add_sound_cue(project.id, scene.id, SoundCue(type="notification"))

    assert db_path.exists()
    assert not (projects_dir / project.id / "project.json").exists()

    reopened = ProjectStore(projects_dir, db_path=db_path)
    loaded = reopened.get(project.id)
    assert loaded.title == "SQLite Demo"
    assert loaded.characters[0].name == "Narrator"
    assert loaded.scenes[0].lines[0].text == "Привет из SQLite."
    assert loaded.scenes[0].cues[0].type == "notification"
    assert [p.id for p in reopened.list_projects()] == [project.id]


def test_project_store_raises_for_missing_sqlite_project(tmp_path):
    store = ProjectStore(tmp_path / "projects", db_path=tmp_path / "actvoice.sqlite3")
    with pytest.raises(ProjectNotFound):
        store.get("missing")


def test_agent_auth_store_persists_hashes_in_sqlite(tmp_path):
    db_path = tmp_path / "actvoice.sqlite3"
    auth = AgentAuthStore(db_path=db_path)
    response = auth.register(AgentRegistrationRequest(agent_name="Hermes", purpose="test"))

    assert response.api_key.startswith("av_")
    assert auth.verify(response.api_key)

    reopened = AgentAuthStore(db_path=db_path)
    assert reopened.verify(response.api_key)
    assert not reopened.verify("av_wrong")

    raw = db_path.read_bytes()
    assert response.api_key.encode("utf-8") not in raw
