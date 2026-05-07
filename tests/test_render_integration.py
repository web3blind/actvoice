from __future__ import annotations

import shutil

import pytest

from app.models import Character, DialogueLine, Scene, SoundCue
from app.render import RenderService
from app.store import ProjectStore
from app.tts import RHVoiceProvider


def test_render_short_project_with_rhvoice(tmp_path):
    if not RHVoiceProvider().is_available() or not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("RHVoice/ffmpeg/ffprobe not available")

    store = ProjectStore(tmp_path)
    project = store.create_project("Mini", "ru")
    character = Character(name="Narrator", voice="aleksandr")
    project = store.add_character(project.id, character)
    scene = Scene(title="Intro", ambience="room_tone")
    project = store.add_scene(project.id, scene)
    store.add_line(project.id, scene.id, DialogueLine(speaker_id=character.id, text="Акт войс. Тест."))
    store.add_sound_cue(project.id, scene.id, SoundCue(type="notification", start_ms=100, duration_ms=400, level=0.15))

    service = RenderService(store)
    job = service.render_final_mix(project.id)

    assert job.status == "done"
    assert job.artifact is not None
    assert job.artifact.mp3_path is not None
    assert job.artifact.duration_sec and job.artifact.duration_sec > 0
