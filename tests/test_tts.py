from __future__ import annotations

import pytest

from app.tts import RHVoiceProvider


def test_rhvoice_lists_installed_voices():
    provider = RHVoiceProvider()
    if not provider.is_available():
        pytest.skip("RHVoice is not installed")
    voices = provider.list_voices()
    ids = {voice.id for voice in voices}
    assert "aleksandr" in ids
    assert any(voice.language_hint == "en" for voice in voices)
