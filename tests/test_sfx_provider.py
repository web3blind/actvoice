from __future__ import annotations

import wave

from app.sfx import synth_sound
from app.sfx_provider import OpenverseSFXProvider


class FakeResponse:
    def __init__(self, payload=None, content=b"", status_code=200):
        self._payload = payload
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_openverse_provider_search_downloads_and_conforms_audio(tmp_path, monkeypatch):
    source_wav = tmp_path / "source.wav"
    synth_sound(source_wav, "notification", 700, level=0.2)
    source_bytes = source_wav.read_bytes()

    def fake_get(url, **kwargs):
        if "api.openverse.org" in url:
            return FakeResponse(
                {
                    "results": [
                        {
                            "id": "sound-1",
                            "title": "Forest Birds",
                            "url": "https://cdn.example.test/birds.wav",
                            "foreign_landing_url": "https://example.test/birds",
                            "creator": "Recorder",
                            "license": "cc0",
                            "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                            "source": "freesound",
                        }
                    ]
                }
            )
        return FakeResponse(content=source_bytes)

    monkeypatch.setattr("app.sfx_provider.requests.get", fake_get)
    provider = OpenverseSFXProvider(cache_dir=tmp_path / "cache")

    result = provider.get_sound("birds", duration_ms=1200)

    assert result.audio_path.exists()
    assert result.metadata["provider"] == "openverse"
    assert result.metadata["license"] == "cc0"
    assert result.metadata["title"] == "Forest Birds"
    with wave.open(str(result.audio_path), "rb") as wf:
        assert wf.getframerate() == 24000
        assert 28000 <= wf.getnframes() <= 29000
