from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class TTSProviderName(str, Enum):
    rhvoice = "rhvoice"
    openai_byo_key = "openai_byo_key"
    edge = "edge"


class RenderStatus(str, Enum):
    queued = "queued"
    rendering = "rendering"
    done = "done"
    failed = "failed"


class Character(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str
    gender_hint: Optional[str] = None
    provider: TTSProviderName = TTSProviderName.rhvoice
    voice: str = "aleksandr"

    @field_validator("name", "voice")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class DialogueLine(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    speaker_id: str
    text: str
    pause_after_ms: int = 500
    rate: int = 100
    pitch: int = 100
    volume: int = 100

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value

    @field_validator("pause_after_ms")
    @classmethod
    def _pause_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("pause_after_ms must be >= 0")
        return value


class SoundCueAnchor(BaseModel):
    """Relative timing anchor for a sound cue.

    The core renderer stays deterministic and AI-free: agents or users choose the
    anchor, then ActVoice resolves it into an absolute start_ms from measured line
    timings during render.
    """

    type: str = "scene_start"
    line_id: Optional[str] = None
    offset_ms: int = 0

    @field_validator("type")
    @classmethod
    def _type_supported(cls, value: str) -> str:
        value = value.strip().lower()
        allowed = {"scene_start", "scene_end", "before_line", "after_line"}
        if value not in allowed:
            raise ValueError(f"anchor type must be one of: {', '.join(sorted(allowed))}")
        return value

    @field_validator("line_id")
    @classmethod
    def _line_id_not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("line_id must not be blank")
        return value


class SoundCue(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    type: str
    start_ms: int = 0
    duration_ms: int = 1000
    level: float = 0.25
    attributes: Dict[str, Any] = Field(default_factory=dict)
    anchor: Optional[SoundCueAnchor] = None

    @field_validator("type")
    @classmethod
    def _type_not_blank(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("type must not be blank")
        return value

    @field_validator("start_ms", "duration_ms")
    @classmethod
    def _time_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("time fields must be >= 0")
        return value

    @field_validator("level")
    @classmethod
    def _level_range(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("level must be between 0 and 1")
        return value


class Scene(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    title: str
    ambience: Optional[str] = "room_tone"
    lines: List[DialogueLine] = Field(default_factory=list)
    cues: List[SoundCue] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class Artifact(BaseModel):
    mp3_path: Optional[str] = None
    wav_path: Optional[str] = None
    duration_sec: Optional[float] = None
    render_manifest_path: Optional[str] = None
    mp3_url: Optional[str] = None
    wav_url: Optional[str] = None
    render_manifest_url: Optional[str] = None


class Project(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    title: str
    language: str = "ru"
    characters: List[Character] = Field(default_factory=list)
    scenes: List[Scene] = Field(default_factory=list)
    artifact: Artifact = Field(default_factory=Artifact)

    @field_validator("title", "language")
    @classmethod
    def _project_text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class RenderJob(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    project_id: str
    status: RenderStatus = RenderStatus.queued
    progress: float = 0.0
    error: Optional[str] = None
    artifact: Optional[Artifact] = None
