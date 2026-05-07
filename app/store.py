from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, List

from app.config import PROJECTS_DIR, SQLITE_DB_PATH
from app.models import Character, DialogueLine, Project, Scene, SoundCue


class ProjectNotFound(KeyError):
    pass


class ProjectStore:
    def __init__(self, root: Path = PROJECTS_DIR, db_path: Path | None = None):
        self.root = Path(root)
        self.db_path = Path(db_path) if db_path is not None else SQLITE_DB_PATH
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def project_dir(self, project_id: str) -> Path:
        # Audio artifacts stay on disk; project manifests live in SQLite.
        return self.root / project_id

    def project_path(self, project_id: str) -> Path:
        # Legacy JSON path kept for migration/backward compatibility.
        return self.project_dir(project_id) / "project.json"

    def create_project(self, title: str, language: str = "ru") -> Project:
        project = Project(title=title, language=language)
        self.save(project)
        return project

    def save(self, project: Project) -> None:
        self.project_dir(project.id).mkdir(parents=True, exist_ok=True)
        payload = json.dumps(_model_to_dict(project), ensure_ascii=False, indent=2)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, data, updated_at)
                VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                ON CONFLICT(id) DO UPDATE SET
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (project.id, payload),
            )

    def get(self, project_id: str) -> Project:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is not None:
            return _project_from_json(row["data"])

        legacy_path = self.project_path(project_id)
        if legacy_path.exists():
            project = _project_from_json(legacy_path.read_text(encoding="utf-8"))
            self.save(project)
            return project

        raise ProjectNotFound(project_id)

    def add_character(self, project_id: str, character: Character) -> Project:
        project = self.get(project_id)
        project.characters.append(character)
        self.save(project)
        return project

    def add_scene(self, project_id: str, scene: Scene) -> Project:
        project = self.get(project_id)
        project.scenes.append(scene)
        self.save(project)
        return project

    def add_line(self, project_id: str, scene_id: str, line: DialogueLine) -> Project:
        project = self.get(project_id)
        scene = self._find_scene(project, scene_id)
        if not any(ch.id == line.speaker_id for ch in project.characters):
            raise ValueError(f"unknown speaker_id: {line.speaker_id}")
        scene.lines.append(line)
        self.save(project)
        return project

    def add_sound_cue(self, project_id: str, scene_id: str, cue: SoundCue) -> Project:
        project = self.get(project_id)
        scene = self._find_scene(project, scene_id)
        scene.cues.append(cue)
        self.save(project)
        return project

    def list_projects(self) -> List[Project]:
        with self._connect() as conn:
            rows = conn.execute("SELECT data FROM projects ORDER BY created_at, id").fetchall()
        projects = [_project_from_json(row["data"]) for row in rows]

        known_ids = {project.id for project in projects}
        for path in sorted(self.root.glob("*/project.json")):
            project = _project_from_json(path.read_text(encoding="utf-8"))
            if project.id in known_ids:
                continue
            self.save(project)
            projects.append(project)
        return projects

    @staticmethod
    def _find_scene(project: Project, scene_id: str) -> Scene:
        for scene in project.scenes:
            if scene.id == scene_id:
                return scene
        raise ValueError(f"unknown scene_id: {scene_id}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
                """
            )


def _model_to_dict(model: Any) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def _project_from_json(raw: str) -> Project:
    if hasattr(Project, "model_validate_json"):
        return Project.model_validate_json(raw)
    return Project.parse_raw(raw)
