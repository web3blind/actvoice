from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from app.config import DEFAULT_SAMPLE_RATE
from app.sfx import synth_sound


DEFAULT_OPENVERSE_QUERIES = {
    "brook": "brook stream water",
    "stream": "brook stream water",
    "creek": "brook stream water",
    "ручей": "brook stream water",
    "birds": "forest birds",
    "birdsong": "forest birds",
    "forest_birds": "forest birds",
    "птицы": "forest birds",
    "footsteps": "footsteps gravel walking",
    "footstep": "footsteps gravel walking",
    "laptop_close": "laptop close",
    "laptop_lid": "laptop close",
    "lid_close": "laptop close",
}


@dataclass
class SFXResult:
    audio_path: Path
    metadata: dict[str, Any]


class OpenverseSFXProvider:
    """Fetch CC0 sound effects from Openverse and conform them for ActVoice.

    Openverse often returns long ambience files. The renderer still controls timing:
    this provider trims or loops the downloaded audio to exactly the requested duration.
    """

    api_url = "https://api.openverse.org/v1/audio/"

    def __init__(self, cache_dir: Path, timeout: int = 30):
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.raw_dir = cache_dir / "raw"
        self.ready_dir = cache_dir / "ready"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.ready_dir.mkdir(parents=True, exist_ok=True)

    def get_sound(
        self,
        cue_type: str,
        duration_ms: int,
        *,
        query: str | None = None,
        license: str = "cc0",
    ) -> SFXResult:
        cue_type = cue_type.lower().strip()
        query = query or DEFAULT_OPENVERSE_QUERIES.get(cue_type, cue_type.replace("_", " "))
        item = self.search_one(query=query, license=license)
        if item is None:
            return self._synthetic_fallback(cue_type, duration_ms, query=query)
        raw_path = self._download(item)
        ready_path = self._conform(raw_path, cue_type=cue_type, duration_ms=duration_ms, item=item)
        metadata = self._metadata(item, query=query, fallback=False)
        metadata["cached_path"] = str(ready_path)
        return SFXResult(audio_path=ready_path, metadata=metadata)

    def search_one(self, query: str, license: str = "cc0") -> dict[str, Any] | None:
        response = requests.get(
            self.api_url,
            params={"q": query, "license": license, "page_size": 8},
            timeout=self.timeout,
            headers={"User-Agent": "ActVoice/0.1 audio drama service"},
        )
        response.raise_for_status()
        for item in response.json().get("results", []):
            url = item.get("url")
            if url and item.get("license") == license:
                return item
        return None

    def _download(self, item: dict[str, Any]) -> Path:
        url = item["url"]
        suffix = _safe_suffix(url) or ".audio"
        raw_name = _hash(url) + suffix
        raw_path = self.raw_dir / raw_name
        meta_path = raw_path.with_suffix(raw_path.suffix + ".json")
        if raw_path.exists() and raw_path.stat().st_size > 0:
            return raw_path
        response = requests.get(url, timeout=self.timeout, headers={"User-Agent": "ActVoice/0.1 audio drama service"})
        response.raise_for_status()
        raw_path.write_bytes(response.content)
        meta_path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        return raw_path

    def _conform(self, raw_path: Path, *, cue_type: str, duration_ms: int, item: dict[str, Any]) -> Path:
        duration_sec = max(0.05, duration_ms / 1000)
        ready_name = f"{cue_type}_{_hash(str(raw_path) + str(duration_ms) + item.get('id', ''))}.wav"
        ready_path = self.ready_dir / ready_name
        if ready_path.exists() and ready_path.stat().st_size > 0:
            return ready_path

        # -stream_loop -1 lets short samples repeat; -t trims long ambience down.
        self._run([
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-stream_loop",
            "-1",
            "-i",
            str(raw_path),
            "-t",
            f"{duration_sec:.3f}",
            "-ar",
            str(DEFAULT_SAMPLE_RATE),
            "-ac",
            "1",
            "-af",
            "afade=t=in:st=0:d=0.03,afade=t=out:st={:.3f}:d=0.03".format(max(0.0, duration_sec - 0.03)),
            str(ready_path),
        ])
        return ready_path

    def _synthetic_fallback(self, cue_type: str, duration_ms: int, *, query: str) -> SFXResult:
        fallback_path = self.ready_dir / f"synthetic_{cue_type}_{duration_ms}.wav"
        synth_sound(fallback_path, cue_type, duration_ms)
        return SFXResult(
            audio_path=fallback_path,
            metadata={
                "provider": "synthetic",
                "query": query,
                "license": "generated",
                "title": cue_type,
                "fallback": True,
                "cached_path": str(fallback_path),
            },
        )

    @staticmethod
    def _metadata(item: dict[str, Any], *, query: str, fallback: bool) -> dict[str, Any]:
        return {
            "provider": "openverse",
            "query": query,
            "id": item.get("id"),
            "title": item.get("title"),
            "creator": item.get("creator"),
            "license": item.get("license"),
            "license_url": item.get("license_url"),
            "source": item.get("source") or item.get("provider"),
            "landing_url": item.get("foreign_landing_url"),
            "duration_ms_original": item.get("duration"),
            "fallback": fallback,
        }

    @staticmethod
    def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"command failed: {' '.join(cmd)}\n{result.stderr}")
        return result


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _safe_suffix(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{2,5}", suffix):
        return suffix
    return ""
