from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.models import Character, DialogueLine, Scene, SoundCue
from app.render import RenderService
from app.store import ProjectStore
from app.tts import RHVoiceProvider


class ActVoiceTools:
    """MCP-ready tool facade.

    These functions intentionally call the same service layer as REST endpoints.
    A real MCP transport can wrap this class without duplicating business logic.
    """

    def __init__(self, store: Optional[ProjectStore] = None):
        self.store = store or ProjectStore()
        self.render_service = RenderService(self.store)

    def create_audio_drama_project(self, title: str, language: str = "ru") -> Dict[str, Any]:
        return _dump(self.store.create_project(title=title, language=language))

    def list_voices(self) -> list[dict[str, Any]]:
        return [voice.__dict__ for voice in RHVoiceProvider().list_voices()]

    def add_character(
        self,
        project_id: str,
        name: str,
        voice: str = "aleksandr",
        gender_hint: str | None = None,
        provider: str = "rhvoice",
    ) -> Dict[str, Any]:
        character = Character(name=name, voice=voice, gender_hint=gender_hint, provider=provider)
        return _dump(self.store.add_character(project_id, character))

    def add_scene(
        self,
        project_id: str,
        title: str,
        ambience: str | None = "room_tone",
    ) -> Dict[str, Any]:
        scene = Scene(title=title, ambience=ambience)
        return _dump(self.store.add_scene(project_id, scene))

    def add_dialogue_line(
        self,
        project_id: str,
        scene_id: str,
        speaker_id: str,
        text: str,
        pause_after_ms: int = 500,
    ) -> Dict[str, Any]:
        line = DialogueLine(speaker_id=speaker_id, text=text, pause_after_ms=pause_after_ms)
        return _dump(self.store.add_line(project_id, scene_id, line))

    def add_sound_cue(
        self,
        project_id: str,
        scene_id: str,
        cue_type: str,
        start_ms: int = 0,
        duration_ms: int = 1000,
        level: float = 0.25,
        attributes: dict[str, Any] | None = None,
        anchor: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        cue = SoundCue(
            type=cue_type,
            start_ms=start_ms,
            duration_ms=duration_ms,
            level=level,
            attributes=attributes or {},
            anchor=anchor,
        )
        return _dump(self.store.add_sound_cue(project_id, scene_id, cue))

    def render_final_mix(self, project_id: str) -> Dict[str, Any]:
        return _dump(self.render_service.render_final_mix(project_id))

    def get_render_status(self, job_id: str) -> Dict[str, Any]:
        return _dump(self.render_service.get_job(job_id))

    def get_final_artifact(self, project_id: str) -> Dict[str, Any]:
        project = self.store.get(project_id)
        return _dump(project.artifact)


def _dump(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
