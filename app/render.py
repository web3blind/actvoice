from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List

from app.config import DEFAULT_SAMPLE_RATE
from app.models import Artifact, Project, RenderJob, RenderStatus
from app.sfx import silence, synth_sound
from app.sfx_provider import DEFAULT_OPENVERSE_QUERIES, OpenverseSFXProvider
from app.store import ProjectStore
from app.tts import RHVoiceProvider


class RenderService:
    def __init__(self, store: ProjectStore, tts_provider: RHVoiceProvider | None = None, sfx_provider: OpenverseSFXProvider | None = None):
        self.store = store
        self.tts_provider = tts_provider or RHVoiceProvider()
        self.sfx_provider = sfx_provider
        self.jobs: Dict[str, RenderJob] = {}

    def render_final_mix(self, project_id: str) -> RenderJob:
        job = RenderJob(project_id=project_id, status=RenderStatus.queued, progress=0.0)
        self.jobs[job.id] = job
        try:
            job.status = RenderStatus.rendering
            job.progress = 0.05
            project = self.store.get(project_id)
            artifact = self._render(project, job)
            job.artifact = artifact
            job.status = RenderStatus.done
            job.progress = 1.0
            project.artifact = artifact
            self.store.save(project)
        except Exception as exc:  # noqa: BLE001 - API should expose job failure instead of crashing
            job.status = RenderStatus.failed
            job.error = str(exc)
        return job

    def get_job(self, job_id: str) -> RenderJob:
        return self.jobs[job_id]

    def _render(self, project: Project, job: RenderJob) -> Artifact:
        project_dir = self.store.project_dir(project.id)
        build_dir = project_dir / "build"
        lines_dir = build_dir / "lines"
        scenes_dir = build_dir / "scenes"
        lines_dir.mkdir(parents=True, exist_ok=True)
        scenes_dir.mkdir(parents=True, exist_ok=True)

        characters = {character.id: character for character in project.characters}
        scene_files: List[Path] = []
        manifest = {"project_id": project.id, "scenes": []}
        total_scenes = max(1, len(project.scenes))

        for scene_index, scene in enumerate(project.scenes):
            scene_parts: List[Path] = []
            line_timings = []
            cursor_ms = 0
            for line_index, line in enumerate(scene.lines):
                character = characters.get(line.speaker_id)
                if character is None:
                    raise ValueError(f"unknown speaker_id: {line.speaker_id}")
                wav = lines_dir / f"{scene.id}_{line_index:03d}_{line.id}.wav"
                self.tts_provider.synthesize(
                    text=line.text,
                    voice=character.voice,
                    output_path=wav,
                    rate=line.rate,
                    pitch=line.pitch,
                    volume=line.volume,
                )
                speech_duration_ms = int(round(self._duration_sec(wav) * 1000))
                line_timings.append(
                    {
                        "id": line.id,
                        "speaker_id": line.speaker_id,
                        "start_ms": cursor_ms,
                        "duration_ms": speech_duration_ms,
                        "pause_after_ms": line.pause_after_ms,
                        "end_ms": cursor_ms + speech_duration_ms,
                    }
                )
                scene_parts.append(wav)
                cursor_ms += speech_duration_ms
                if line.pause_after_ms:
                    pause = lines_dir / f"{scene.id}_{line_index:03d}_{line.id}_pause.wav"
                    silence(pause, line.pause_after_ms)
                    scene_parts.append(pause)
                    cursor_ms += line.pause_after_ms

            if not scene_parts:
                empty = scenes_dir / f"{scene.id}_empty.wav"
                silence(empty, 1000)
                scene_parts.append(empty)

            dialogue = scenes_dir / f"{scene.id}_dialogue.wav"
            self._concat_wavs(scene_parts, dialogue)
            duration_ms = int(round(self._duration_sec(dialogue) * 1000))
            sfx_provider = self.sfx_provider or OpenverseSFXProvider(build_dir / "sfx_cache")
            ambience = scenes_dir / f"{scene.id}_ambience.wav"
            ambience_meta = self._prepare_sound(
                sfx_provider=sfx_provider,
                cue_type=scene.ambience or "room_tone",
                duration_ms=duration_ms,
                output_path=ambience,
                level=0.08,
            )

            mix_inputs = [ambience, dialogue]
            delays = [0, 0]
            cue_metadata = []
            for cue_index, cue in enumerate(scene.cues):
                cue_wav = scenes_dir / f"{scene.id}_cue_{cue_index:03d}_{cue.type}.wav"
                resolved_start_ms = self._resolve_cue_start_ms(cue, duration_ms, line_timings)
                cue_meta = self._prepare_sound(
                    sfx_provider=sfx_provider,
                    cue_type=cue.type,
                    duration_ms=cue.duration_ms,
                    output_path=cue_wav,
                    level=cue.level,
                    query=cue.attributes.get("query") if cue.attributes else None,
                )
                cue_metadata.append(
                    {
                        "id": cue.id,
                        "type": cue.type,
                        "requested_start_ms": cue.start_ms,
                        "start_ms": resolved_start_ms,
                        "duration_ms": cue.duration_ms,
                        "level": cue.level,
                        "resolved_anchor": self._anchor_to_manifest(cue),
                        **cue_meta,
                    }
                )
                mix_inputs.append(cue_wav)
                delays.append(resolved_start_ms)

            mixed = scenes_dir / f"{scene.id}_mixed.wav"
            self._mix_wavs(mix_inputs, delays, mixed)
            scene_files.append(mixed)
            manifest["scenes"].append(
                {
                    "id": scene.id,
                    "title": scene.title,
                    "dialogue_duration_ms": duration_ms,
                    "timing_map": {"lines": line_timings},
                    "ambience": {"type": scene.ambience or "room_tone", **ambience_meta},
                    "cue_count": len(scene.cues),
                    "cues": cue_metadata,
                    "file": str(mixed),
                }
            )
            job.progress = 0.1 + 0.75 * ((scene_index + 1) / total_scenes)

        final_wav = build_dir / "final_mix.wav"
        self._concat_wavs(scene_files, final_wav)
        final_mp3 = build_dir / "final_mix.mp3"
        self._run([
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(final_wav),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(final_mp3),
        ])
        duration_sec = self._duration_sec(final_mp3)
        manifest_path = build_dir / "render_manifest.json"
        manifest["artifact"] = {"mp3": str(final_mp3), "wav": str(final_wav), "duration_sec": duration_sec}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return Artifact(
            mp3_path=str(final_mp3),
            wav_path=str(final_wav),
            duration_sec=duration_sec,
            render_manifest_path=str(manifest_path),
            mp3_url=f"/api/projects/{project.id}/artifact.mp3",
            wav_url=f"/api/projects/{project.id}/artifact.wav",
            render_manifest_url=f"/api/projects/{project.id}/render-manifest.json",
        )

    def _resolve_cue_start_ms(self, cue, scene_duration_ms: int, line_timings: list[dict]) -> int:
        if cue.anchor is None:
            return cue.start_ms

        anchor = cue.anchor
        if anchor.type == "scene_start":
            resolved = anchor.offset_ms
        elif anchor.type == "scene_end":
            resolved = scene_duration_ms + anchor.offset_ms
        else:
            if not anchor.line_id:
                raise ValueError(f"line_id is required for {anchor.type} sound cue anchor")
            line_timing = next((line for line in line_timings if line["id"] == anchor.line_id), None)
            if line_timing is None:
                raise ValueError(f"unknown line_id in sound cue anchor: {anchor.line_id}")
            if anchor.type == "before_line":
                resolved = line_timing["start_ms"] + anchor.offset_ms
            elif anchor.type == "after_line":
                resolved = line_timing["end_ms"] + anchor.offset_ms
            else:  # pragma: no cover - model validation prevents this
                raise ValueError(f"unsupported sound cue anchor type: {anchor.type}")

        if resolved < 0:
            raise ValueError(f"sound cue anchor resolves before scene start: {resolved}ms")
        return int(resolved)

    @staticmethod
    def _anchor_to_manifest(cue) -> dict | None:
        if cue.anchor is None:
            return None
        return cue.anchor.model_dump(mode="json") if hasattr(cue.anchor, "model_dump") else cue.anchor.dict()

    def _prepare_sound(
        self,
        *,
        sfx_provider: OpenverseSFXProvider,
        cue_type: str,
        duration_ms: int,
        output_path: Path,
        level: float,
        query: str | None = None,
    ) -> dict:
        cue_key = cue_type.lower().strip()
        try_openverse = query is not None or cue_key in DEFAULT_OPENVERSE_QUERIES
        if try_openverse:
            try:
                result = sfx_provider.get_sound(cue_key, duration_ms, query=query)
                self._run([
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(result.audio_path),
                    "-af",
                    f"volume={level}",
                    "-ar",
                    str(DEFAULT_SAMPLE_RATE),
                    "-ac",
                    "1",
                    str(output_path),
                ])
                return result.metadata
            except Exception as exc:  # noqa: BLE001 - sound search should not fail the render
                synth_sound(output_path, cue_key, duration_ms, level=level)
                return {"provider": "synthetic", "fallback": True, "error": str(exc), "query": query}
        synth_sound(output_path, cue_key, duration_ms, level=level)
        return {"provider": "synthetic", "fallback": False, "query": query}

    def _concat_wavs(self, inputs: List[Path], output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        list_file = output.with_suffix(".concat.txt")
        list_file.write_text("".join(f"file '{p.resolve()}'\n" for p in inputs), encoding="utf-8")
        self._run([
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-ar",
            str(DEFAULT_SAMPLE_RATE),
            "-ac",
            "1",
            str(output),
        ])

    def _mix_wavs(self, inputs: List[Path], delays_ms: List[int], output: Path) -> None:
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        for path in inputs:
            cmd.extend(["-i", str(path)])
        chains = []
        labels = []
        for idx, delay in enumerate(delays_ms):
            label = f"a{idx}"
            volume = "0.70" if idx == 1 else "1.0"
            chains.append(f"[{idx}:a]adelay={delay}:all=1,volume={volume}[{label}]")
            labels.append(f"[{label}]")
        chains.append("".join(labels) + f"amix=inputs={len(inputs)}:duration=longest:normalize=0[out]")
        cmd.extend(["-filter_complex", ";".join(chains), "-map", "[out]", "-ar", str(DEFAULT_SAMPLE_RATE), "-ac", "1", str(output)])
        self._run(cmd)

    def _duration_sec(self, path: Path) -> float:
        result = self._run([
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ])
        return float(result.stdout.strip())

    @staticmethod
    def _run(cmd: List[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"command failed: {' '.join(cmd)}\n{result.stderr}")
        return result
