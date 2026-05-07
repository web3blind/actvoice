from __future__ import annotations

import math
import wave
from pathlib import Path


def _noise(seed: int):
    state = seed & 0x7FFFFFFF
    while True:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        yield (state / 0x7FFFFFFF) * 2 - 1

from app.config import DEFAULT_SAMPLE_RATE


def _clamp(sample: float) -> int:
    return max(-32767, min(32767, int(sample * 32767)))


def _write_mono_wav(path: Path, samples: list[float], sample_rate: int = DEFAULT_SAMPLE_RATE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = b"".join(_clamp(s).to_bytes(2, "little", signed=True) for s in samples)
        wf.writeframes(frames)
    return path


def silence(path: Path, duration_ms: int, sample_rate: int = DEFAULT_SAMPLE_RATE) -> Path:
    count = int(sample_rate * duration_ms / 1000)
    return _write_mono_wav(path, [0.0] * count, sample_rate)


def synth_sound(
    path: Path,
    cue_type: str,
    duration_ms: int,
    *,
    level: float = 0.25,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> Path:
    cue_type = cue_type.lower().strip()
    count = max(1, int(sample_rate * duration_ms / 1000))
    samples: list[float] = []

    if cue_type in {"notification", "beep"}:
        for i in range(count):
            t = i / sample_rate
            env = min(1.0, i / (sample_rate * 0.02)) * max(0.0, 1 - i / count)
            samples.append(level * env * math.sin(2 * math.pi * 880 * t))
    elif cue_type in {"heartbeat", "pulse"}:
        for i in range(count):
            phase = (i / sample_rate) % 1.0
            hit = math.exp(-90 * phase) + 0.65 * math.exp(-120 * max(0, phase - 0.18))
            samples.append(level * min(1.0, hit) * math.sin(2 * math.pi * 70 * i / sample_rate))
    elif cue_type in {"footsteps", "footstep"}:
        for i in range(count):
            phase = (i / sample_rate) % 0.55
            thump = math.exp(-80 * phase) * math.sin(2 * math.pi * 95 * i / sample_rate)
            click = math.exp(-180 * phase) * math.sin(2 * math.pi * 450 * i / sample_rate)
            samples.append(level * (0.8 * thump + 0.2 * click))
    elif cue_type in {"water_drip", "drip"}:
        for i in range(count):
            phase = (i / sample_rate) % 1.4
            drop = math.exp(-35 * phase) * (
                0.7 * math.sin(2 * math.pi * 650 * i / sample_rate)
                + 0.3 * math.sin(2 * math.pi * 1200 * i / sample_rate)
            )
            samples.append(level * drop)
    elif cue_type in {"tension", "tension_pad", "drone"}:
        for i in range(count):
            t = i / sample_rate
            samples.append(level * 0.45 * (math.sin(2 * math.pi * 110 * t) + 0.5 * math.sin(2 * math.pi * 147 * t)))
    elif cue_type in {"brook", "stream", "creek", "ручей"}:
        noise = _noise(0xB00C)
        slow = _noise(0x51A7)
        lp = 0.0
        ripple = 0.0
        for i in range(count):
            t = i / sample_rate
            lp = 0.985 * lp + 0.015 * next(noise)
            ripple = 0.92 * ripple + 0.08 * next(slow)
            shimmer = math.sin(2 * math.pi * (420 + 70 * ripple) * t) * 0.08
            current = 0.55 * lp + 0.28 * ripple + shimmer
            samples.append(level * 0.75 * current)
    elif cue_type in {"birds", "birdsong", "forest_birds", "птицы"}:
        noise = _noise(0xB1D5)
        for i in range(count):
            t = i / sample_rate
            sample = 0.0
            for offset, base_freq in ((0.15, 1800), (1.10, 2400), (2.35, 1650), (3.20, 3100)):
                phase = (t + offset) % 4.0
                if phase < 0.22:
                    env = math.sin(math.pi * phase / 0.22) ** 2
                    wobble = 1 + 0.08 * math.sin(2 * math.pi * 18 * t)
                    sample += env * math.sin(2 * math.pi * base_freq * wobble * t)
            sample += 0.015 * next(noise)
            samples.append(level * 0.65 * sample)
    elif cue_type in {"laptop_close", "laptop_lid", "lid_close"}:
        noise = _noise(0xC105E)
        for i in range(count):
            t = i / sample_rate
            thump = math.exp(-45 * t) * math.sin(2 * math.pi * 115 * t)
            clack = math.exp(-120 * max(0.0, t - 0.05)) * math.sin(2 * math.pi * 950 * t) if t >= 0.05 else 0.0
            samples.append(level * (0.65 * thump + 0.25 * clack + 0.08 * next(noise) * math.exp(-20 * t)))
    else:
        # deterministic pseudo-noise bed for room_tone/wind/rain/unknown ambience
        noise = _noise(0x12345678)
        for _ in range(count):
            samples.append(level * 0.35 * next(noise))

    # Soft fade in/out to avoid clicks.
    fade = min(count // 10, int(sample_rate * 0.03))
    if fade > 0:
        for i in range(fade):
            factor = i / fade
            samples[i] *= factor
            samples[-i - 1] *= factor
    return _write_mono_wav(path, samples, sample_rate)
