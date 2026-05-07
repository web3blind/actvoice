from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class VoiceInfo:
    provider: str
    id: str
    language_hint: str


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
    ) -> Path:
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
        return output_path
