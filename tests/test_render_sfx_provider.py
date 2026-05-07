from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.models import Character, DialogueLine, Scene, SoundCue
from app.render import RenderService
from app.sfx import synth_sound
from app.store import ProjectStore


@dataclass
class FakeSFXResult:
    audio_path: Path
    metadata: dict


class FakeOpenverseProvider:
    def __init__(self, root: Path):
        self.root = root
        self.calls = []

    def get_sound(self, cue_type: str, duration_ms: int, *, query=None):
        self.calls.append((cue_type, duration_ms, query))
        out = self.root / f"{cue_type}_{duration_ms}.wav"
        synth_sound(out, "notification", duration_ms, level=0.2)
        return FakeSFXResult(
            audio_path=out,
            metadata={
                "provider": "openverse",
                "title": f"Fake {cue_type}",
                "license": "cc0",
                "query": query or cue_type,
                "fallback": False,
            },
        )


def test_render_uses_openverse_provider_for_known_sfx(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    project = store.create_project("SFX", "ru")
    character = Character(name="Narrator", voice="aleksandr")
    project = store.add_character(project.id, character)
    scene = Scene(title="Nature", ambience="brook")
    project = store.add_scene(project.id, scene)
    store.add_line(project.id, scene.id, DialogueLine(speaker_id=character.id, text="Тест звука."))
    store.add_sound_cue(project.id, scene.id, SoundCue(type="birds", start_ms=0, duration_ms=500, level=0.2))

    provider = FakeOpenverseProvider(tmp_path / "fake")
    service = RenderService(store, sfx_provider=provider)
    job = service.render_final_mix(project.id)

    assert job.status == "done"
    cue_names = [call[0] for call in provider.calls]
    assert "brook" in cue_names
    assert "birds" in cue_names

    manifest = json.loads(Path(job.artifact.render_manifest_path).read_text(encoding="utf-8"))
    assert manifest["scenes"][0]["ambience"]["provider"] == "openverse"
    assert manifest["scenes"][0]["cues"][0]["provider"] == "openverse"
    assert manifest["scenes"][0]["cues"][0]["license"] == "cc0"
