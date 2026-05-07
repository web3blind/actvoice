from __future__ import annotations

import json
from pathlib import Path

from app.models import Character, DialogueLine, Scene, SoundCue, SoundCueAnchor
from app.render import RenderService
from app.sfx import silence, synth_sound
from app.store import ProjectStore


class FixedTTSProvider:
    def synthesize(self, *, text, voice, output_path, rate=100, pitch=100, volume=100):
        silence(Path(output_path), 1000)


class FakeSFXResult:
    def __init__(self, audio_path: Path, metadata: dict):
        self.audio_path = audio_path
        self.metadata = metadata


class FakeSFXProvider:
    def __init__(self, root: Path):
        self.root = root
        self.calls = []

    def get_sound(self, cue_type: str, duration_ms: int, *, query=None):
        self.calls.append((cue_type, duration_ms, query))
        out = self.root / f"{cue_type}_{duration_ms}.wav"
        synth_sound(out, "notification", duration_ms, level=0.2)
        return FakeSFXResult(
            out,
            {
                "provider": "openverse",
                "title": f"Fake {cue_type}",
                "license": "cc0",
                "fallback": False,
            },
        )


def test_sound_cue_anchor_model_accepts_relative_line_anchor():
    cue = SoundCue(
        type="laptop_close",
        duration_ms=1200,
        anchor=SoundCueAnchor(type="after_line", line_id="line-a", offset_ms=500),
    )

    assert cue.start_ms == 0
    assert cue.anchor.type == "after_line"
    assert cue.anchor.line_id == "line-a"
    assert cue.anchor.offset_ms == 500


def test_render_resolves_relative_sound_cue_anchors_and_writes_timing_map(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    project = store.create_project("Anchors", "ru")
    character = Character(name="Narrator", voice="aleksandr")
    project = store.add_character(project.id, character)
    scene = Scene(title="Scene", ambience="brook")
    project = store.add_scene(project.id, scene)
    line_one = DialogueLine(speaker_id=character.id, text="Первая реплика.", pause_after_ms=500)
    line_two = DialogueLine(speaker_id=character.id, text="Вторая реплика.", pause_after_ms=0)
    store.add_line(project.id, scene.id, line_one)
    store.add_line(project.id, scene.id, line_two)
    cue = SoundCue(
        type="laptop_close",
        duration_ms=700,
        level=0.4,
        anchor=SoundCueAnchor(type="after_line", line_id=line_one.id, offset_ms=250),
    )
    store.add_sound_cue(project.id, scene.id, cue)

    provider = FakeSFXProvider(tmp_path / "sfx")
    service = RenderService(store, tts_provider=FixedTTSProvider(), sfx_provider=provider)
    job = service.render_final_mix(project.id)

    assert job.status == "done"
    manifest = json.loads(Path(job.artifact.render_manifest_path).read_text(encoding="utf-8"))
    scene_manifest = manifest["scenes"][0]
    assert scene_manifest["timing_map"]["lines"][0]["id"] == line_one.id
    assert scene_manifest["timing_map"]["lines"][0]["start_ms"] == 0
    assert scene_manifest["timing_map"]["lines"][0]["duration_ms"] == 1000
    assert scene_manifest["timing_map"]["lines"][0]["pause_after_ms"] == 500
    assert scene_manifest["timing_map"]["lines"][1]["start_ms"] == 1500

    rendered_cue = scene_manifest["cues"][0]
    assert rendered_cue["requested_start_ms"] == 0
    assert rendered_cue["start_ms"] == 1250
    assert rendered_cue["resolved_anchor"] == {
        "type": "after_line",
        "line_id": line_one.id,
        "offset_ms": 250,
    }


def test_render_fails_cleanly_for_unknown_line_anchor(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    project = store.create_project("Bad anchor", "ru")
    character = Character(name="Narrator", voice="aleksandr")
    project = store.add_character(project.id, character)
    scene = Scene(title="Scene", ambience="room_tone")
    project = store.add_scene(project.id, scene)
    store.add_line(project.id, scene.id, DialogueLine(speaker_id=character.id, text="Текст."))
    store.add_sound_cue(
        project.id,
        scene.id,
        SoundCue(
            type="notification",
            anchor=SoundCueAnchor(type="after_line", line_id="missing-line", offset_ms=0),
        ),
    )

    service = RenderService(store, tts_provider=FixedTTSProvider(), sfx_provider=FakeSFXProvider(tmp_path / "sfx"))
    job = service.render_final_mix(project.id)

    assert job.status == "failed"
    assert "unknown line_id in sound cue anchor" in job.error
