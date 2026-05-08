from __future__ import annotations

import asyncio
import importlib.util
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List


EDGE_DEFAULT_RU_VOICE = "ru-RU-DmitryNeural"
EDGE_DEFAULT_EN_VOICE = "en-US-GuyNeural"
RHVOICE_DEFAULT_RU_VOICE = "aleksandr"
RHVOICE_DEFAULT_EN_VOICE = "alan"


@dataclass(frozen=True)
class VoiceInfo:
    provider: str
    id: str
    language_hint: str


@dataclass(frozen=True)
class SynthesisResult:
    provider: str
    voice: str
    path: Path
    fallback_used: bool = False
    fallback_reason: str | None = None


class RHVoiceProvider:
    name = "rhvoice"

    def __init__(self, executable: str = "RHVoice-test", voices_dir: Path | None = None):
        self.executable = executable
        self.voices_dir = voices_dir or Path("/usr/share/RHVoice/voices")

    def is_available(self) -> bool:
        return shutil.which(self.executable) is not None and self.voices_dir.exists()

    def list_voices(self) -> List[VoiceInfo]:
        if not self.voices_dir.exists():
            return []
        voices: List[VoiceInfo] = []
        for path in sorted(self.voices_dir.iterdir()):
            if not path.is_dir():
                continue
            voice_id = path.name
            lang = "ru" if voice_id in {"aleksandr", "anna", "artemiy", "elena", "irina"} else "en"
            voices.append(VoiceInfo(provider=self.name, id=voice_id, language_hint=lang))
        return voices

    def synthesize(
        self,
        *,
        text: str,
        voice: str,
        output_path: Path,
        rate: int = 100,
        pitch: int = 100,
        volume: int = 100,
    ) -> SynthesisResult:
        if not self.is_available():
            raise RuntimeError("RHVoice-test is not available")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        input_path = output_path.with_suffix(".txt")
        input_path.write_text(text, encoding="utf-8")
        cmd = [
            self.executable,
            "-p",
            voice,
            "-r",
            str(rate),
            "-t",
            str(pitch),
            "-v",
            str(volume),
            "-i",
            str(input_path),
            "-o",
            str(output_path),
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"RHVoice failed: {result.stderr.strip()}")
        return SynthesisResult(provider=self.name, voice=voice, path=output_path)


class EdgeTTSProvider:
    """Microsoft Edge neural TTS provider.

    Uses the community `edge-tts` package when installed. It renders to a
    temporary MP3 and converts to the WAV format expected by the deterministic
    ActVoice renderer. If the package or network is unavailable, callers should
    fall back to RHVoice.
    """

    name = "edge"

    def __init__(self, *, default_ru_voice: str = EDGE_DEFAULT_RU_VOICE, default_en_voice: str = EDGE_DEFAULT_EN_VOICE):
        self.default_ru_voice = default_ru_voice
        self.default_en_voice = default_en_voice

    def is_available(self) -> bool:
        return importlib.util.find_spec("edge_tts") is not None and shutil.which("ffmpeg") is not None

    def list_voices(self) -> List[VoiceInfo]:
        # Static safe defaults keep /api/voices fast and network-free. A future
        # endpoint can expose the full online Edge catalog separately.
        return [
            VoiceInfo(provider=self.name, id=self.default_ru_voice, language_hint="ru"),
            VoiceInfo(provider=self.name, id="ru-RU-SvetlanaNeural", language_hint="ru"),
            VoiceInfo(provider=self.name, id=self.default_en_voice, language_hint="en"),
            VoiceInfo(provider=self.name, id="en-US-JennyNeural", language_hint="en"),
        ]

    def synthesize(
        self,
        *,
        text: str,
        voice: str,
        output_path: Path,
        rate: int = 100,
        pitch: int = 100,
        volume: int = 100,
    ) -> SynthesisResult:
        if not self.is_available():
            raise RuntimeError("edge-tts or ffmpeg is not available")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="actvoice-edge-", suffix=".mp3", delete=False) as tmp:
            mp3_path = Path(tmp.name)
        try:
            asyncio.run(self._save_mp3(text=text, voice=voice, output_path=mp3_path, rate=rate, pitch=pitch, volume=volume))
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(mp3_path),
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    str(output_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg failed converting Edge audio: {result.stderr.strip()}")
            return SynthesisResult(provider=self.name, voice=voice, path=output_path)
        finally:
            mp3_path.unlink(missing_ok=True)

    async def _save_mp3(self, *, text: str, voice: str, output_path: Path, rate: int, pitch: int, volume: int) -> None:
        import edge_tts

        communicate = edge_tts.Communicate(
            text,
            voice,
            rate=_edge_percent(rate),
            pitch=_edge_pitch(pitch),
            volume=_edge_percent(volume),
        )
        await communicate.save(str(output_path))


def _edge_percent(value: int) -> str:
    # RHVoice uses 100 as neutral. Edge expects signed percentages.
    delta = max(-100, min(100, int(value) - 100))
    return f"{delta:+d}%"


def _edge_pitch(value: int) -> str:
    delta = max(-100, min(100, int(value) - 100))
    return f"{delta:+d}Hz"


class FallbackTTSProvider:
    """Provider chain for ActVoice free mode: Edge first, RHVoice fallback."""

    name = "fallback"

    def __init__(
        self,
        *,
        primary=None,
        fallback=None,
        fallback_voice: str | None = None,
        default_provider: str | None = None,
    ):
        self.primary = primary or EdgeTTSProvider()
        self.fallback = fallback or RHVoiceProvider()
        self.fallback_voice = fallback_voice or os.getenv("ACTVOICE_RHVOICE_FALLBACK_VOICE", RHVOICE_DEFAULT_RU_VOICE)
        self.default_provider = (default_provider or os.getenv("ACTVOICE_TTS_DEFAULT", "edge")).lower()

    def is_available(self) -> bool:
        return self.primary.is_available() or self.fallback.is_available()

    def list_voices(self) -> List[VoiceInfo]:
        voices: List[VoiceInfo] = []
        voices.extend(self.primary.list_voices())
        voices.extend(self.fallback.list_voices())
        return voices

    def synthesize(
        self,
        *,
        text: str,
        voice: str,
        output_path: Path,
        rate: int = 100,
        pitch: int = 100,
        volume: int = 100,
        provider: str | None = None,
        fallback_voice: str | None = None,
    ) -> SynthesisResult:
        requested_provider = (provider or self.default_provider).lower()
        if requested_provider == "rhvoice":
            return _normalize_result(
                self.fallback.synthesize(text=text, voice=voice, output_path=output_path, rate=rate, pitch=pitch, volume=volume),
                provider="rhvoice",
                voice=voice,
                output_path=output_path,
            )
        if requested_provider not in {"edge", "free", "default", "fallback"}:
            raise ValueError(f"unsupported TTS provider for free chain: {requested_provider}")

        try:
            return _normalize_result(
                self.primary.synthesize(text=text, voice=voice, output_path=output_path, rate=rate, pitch=pitch, volume=volume),
                provider=getattr(self.primary, "name", "edge"),
                voice=voice,
                output_path=output_path,
            )
        except Exception as exc:  # noqa: BLE001 - fallback is the product behavior
            fallback_voice_id = fallback_voice or self.fallback_voice
            result = _normalize_result(
                self.fallback.synthesize(
                    text=text,
                    voice=fallback_voice_id,
                    output_path=output_path,
                    rate=rate,
                    pitch=pitch,
                    volume=volume,
                ),
                provider=getattr(self.fallback, "name", "rhvoice"),
                voice=fallback_voice_id,
                output_path=output_path,
            )
            return SynthesisResult(
                provider=result.provider,
                voice=result.voice,
                path=result.path,
                fallback_used=True,
                fallback_reason=str(exc),
            )


def _normalize_result(result, *, provider: str, voice: str, output_path: Path) -> SynthesisResult:
    if isinstance(result, SynthesisResult):
        return result
    return SynthesisResult(provider=provider, voice=voice, path=Path(output_path))


def default_tts_provider() -> FallbackTTSProvider | RHVoiceProvider | EdgeTTSProvider:
    mode = os.getenv("ACTVOICE_TTS_MODE", "free").lower()
    if mode in {"rhvoice", "local", "offline"}:
        return RHVoiceProvider()
    if mode == "edge":
        return EdgeTTSProvider()
    return FallbackTTSProvider()
