from __future__ import annotations

import wave

from app.sfx import synth_sound


def test_synth_sound_writes_wav(tmp_path):
    out = tmp_path / "notification.wav"
    synth_sound(out, "notification", 500, level=0.2)
    assert out.exists()
    with wave.open(str(out), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 24000
        assert wf.getnframes() > 0


def test_nature_sound_cues_are_distinct_enough_for_storytelling(tmp_path):
    brook = tmp_path / "brook.wav"
    birds = tmp_path / "birds.wav"
    laptop = tmp_path / "laptop.wav"

    synth_sound(brook, "brook", 1200, level=0.25)
    synth_sound(birds, "birds", 1200, level=0.25)
    synth_sound(laptop, "laptop_close", 500, level=0.25)

    assert brook.exists()
    assert birds.exists()
    assert laptop.exists()
    assert brook.read_bytes() != birds.read_bytes()
    assert laptop.stat().st_size < brook.stat().st_size
