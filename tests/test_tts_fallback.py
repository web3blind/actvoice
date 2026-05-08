from __future__ import annotations

import json
from pathlib import Path

from app.models import Character, DialogueLine, Scene, TTSProviderName
from app.render import RenderService
from app.sfx import silence
from app.store import ProjectStore
from app.tts import FallbackTTSProvider, SynthesisResult, VoiceInfo


class FakeEdgeProvider:
    name = "edge"

    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = []

    def is_available(self):
        return True

    def list_voices(self):
        return [VoiceInfo(provider="edge", id="ru-RU-DmitryNeural", language_hint="ru")]

    def synthesize(self, *, text, voice, output_path, rate=100, pitch=100, volume=100):
        self.calls.append((text, voice, output_path))
        if self.fail:
            raise RuntimeError("edge unavailable")
        silence(Path(output_path), 600)
        return SynthesisResult(provider="edge", voice=voice, path=Path(output_path), fallback_used=False)


class FakeRHVoiceProvider:
    name = "rhvoice"

    def __init__(self):
        self.calls = []

    def is_available(self):
        return True

    def list_voices(self):
        return [VoiceInfo(provider="rhvoice", id="aleksandr", language_hint="ru")]

    def synthesize(self, *, text, voice, output_path, rate=100, pitch=100, volume=100):
        self.calls.append((text, voice, output_path))
        silence(Path(output_path), 600)
        return SynthesisResult(provider="rhvoice", voice=voice, path=Path(output_path), fallback_used=False)


def _render_one_line(tmp_path, tts_provider, *, provider=TTSProviderName.edge, voice="ru-RU-DmitryNeural"):
    store = ProjectStore(tmp_path / "projects")
    project = store.create_project("TTS fallback", "ru")
    character = Character(name="Narrator", provider=provider, voice=voice)
    project = store.add_character(project.id, character)
    scene = Scene(title="Intro", ambience="room_tone")
    project = store.add_scene(project.id, scene)
    store.add_line(project.id, scene.id, DialogueLine(speaker_id=character.id, text="Проверка голоса."))

    service = RenderService(store, tts_provider=tts_provider, sfx_provider=None)
    job = service.render_final_mix(project.id)
    assert job.status == "done", job.error
    manifest = json.loads(Path(job.artifact.render_manifest_path).read_text(encoding="utf-8"))
    return manifest


def test_free_tts_chain_uses_edge_first_and_records_manifest_metadata(tmp_path):
    edge = FakeEdgeProvider()
    rhvoice = FakeRHVoiceProvider()
    chain = FallbackTTSProvider(primary=edge, fallback=rhvoice)

    manifest = _render_one_line(tmp_path, chain)

    assert len(edge.calls) == 1
    assert len(rhvoice.calls) == 0
    line = manifest["scenes"][0]["timing_map"]["lines"][0]
    assert line["tts_provider"] == "edge"
    assert line["tts_voice"] == "ru-RU-DmitryNeural"
    assert line["tts_fallback_used"] is False


def test_free_tts_chain_falls_back_to_rhvoice_when_edge_fails(tmp_path):
    edge = FakeEdgeProvider(fail=True)
    rhvoice = FakeRHVoiceProvider()
    chain = FallbackTTSProvider(primary=edge, fallback=rhvoice, fallback_voice="aleksandr")

    manifest = _render_one_line(tmp_path, chain)

    assert len(edge.calls) == 1
    assert len(rhvoice.calls) == 1
    line = manifest["scenes"][0]["timing_map"]["lines"][0]
    assert line["tts_provider"] == "rhvoice"
    assert line["tts_voice"] == "aleksandr"
    assert line["tts_fallback_used"] is True
    assert "edge unavailable" in line["tts_fallback_reason"]


def test_rhvoice_character_provider_keeps_rhvoice_only(tmp_path):
    edge = FakeEdgeProvider()
    rhvoice = FakeRHVoiceProvider()
    chain = FallbackTTSProvider(primary=edge, fallback=rhvoice, fallback_voice="aleksandr")

    manifest = _render_one_line(tmp_path, chain, provider=TTSProviderName.rhvoice, voice="aleksandr")

    assert len(edge.calls) == 0
    assert len(rhvoice.calls) == 1
    line = manifest["scenes"][0]["timing_map"]["lines"][0]
    assert line["tts_provider"] == "rhvoice"
    assert line["tts_voice"] == "aleksandr"
    assert line["tts_fallback_used"] is False
