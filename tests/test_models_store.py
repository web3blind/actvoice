from __future__ import annotations

from app.models import Character, DialogueLine, Project, Scene, SoundCue
from app.store import ProjectStore


def test_project_model_defaults():
    project = Project(title="Тест", language="ru")
    assert project.id
    assert project.characters == []
    assert project.scenes == []


def test_store_create_and_mutate_project(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("Demo", "ru")
    character = Character(name="Narrator", voice="aleksandr")
    project = store.add_character(project.id, character)
    scene = Scene(title="Intro")
    project = store.add_scene(project.id, scene)
    project = store.add_line(project.id, scene.id, DialogueLine(speaker_id=character.id, text="Привет."))
    project = store.add_sound_cue(project.id, scene.id, SoundCue(type="notification"))

    loaded = store.get(project.id)
    assert loaded.characters[0].name == "Narrator"
    assert loaded.scenes[0].lines[0].text == "Привет."
    assert loaded.scenes[0].cues[0].type == "notification"
