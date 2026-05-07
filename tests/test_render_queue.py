from __future__ import annotations

import time
from pathlib import Path

from app.models import Character, DialogueLine, RenderJob, RenderStatus, Scene
from app.render import RenderService
from app.render_queue import RenderQueue
from app.sfx import silence
from app.store import ProjectStore


class FixedTTSProvider:
    def synthesize(self, *, text, voice, output_path, rate=100, pitch=100, volume=100):
        silence(Path(output_path), 500)


def test_render_queue_returns_queued_job_then_completes(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    project = store.create_project("Queued", "ru")
    character = Character(name="Narrator", voice="aleksandr")
    project = store.add_character(project.id, character)
    scene = Scene(title="Intro", ambience="room_tone")
    project = store.add_scene(project.id, scene)
    store.add_line(project.id, scene.id, DialogueLine(speaker_id=character.id, text="Тест очереди."))

    render_service = RenderService(store, tts_provider=FixedTTSProvider(), sfx_provider=None)
    queue = RenderQueue(store, render_service=render_service, max_workers=1)
    job = queue.submit(project.id)

    assert job.status == "queued"
    assert job.progress == 0.0

    deadline = time.time() + 10
    while time.time() < deadline:
        current = queue.get_job(job.id)
        if current.status == "done":
            break
        time.sleep(0.05)

    current = queue.get_job(job.id)
    assert current.status == "done"
    assert current.progress == 1.0
    assert current.artifact is not None
    assert current.artifact.mp3_path
    assert current.artifact.mp3_url == f"/api/projects/{project.id}/artifact.mp3"
    assert Path(current.artifact.mp3_path).exists()

    saved = store.get(project.id)
    assert saved.artifact.mp3_path == current.artifact.mp3_path
    assert saved.artifact.mp3_url == f"/api/projects/{project.id}/artifact.mp3"


def test_render_queue_marks_job_failed_for_missing_project(tmp_path):
    store = ProjectStore(tmp_path / "projects", db_path=tmp_path / "actvoice.sqlite3")
    queue = RenderQueue(store, max_workers=1)
    job = queue.submit("missing-project")

    deadline = time.time() + 10
    while time.time() < deadline:
        current = queue.get_job(job.id)
        if current.status == "failed":
            break
        time.sleep(0.05)

    current = queue.get_job(job.id)
    assert current.status == "failed"
    assert current.error

    reopened_queue = RenderQueue(store, max_workers=1)
    persisted = reopened_queue.get_job(job.id)
    assert persisted.status == "failed"
    assert persisted.error == current.error


def test_render_queue_persists_completed_jobs_across_queue_restart(tmp_path):
    db_path = tmp_path / "actvoice.sqlite3"
    store = ProjectStore(tmp_path / "projects", db_path=db_path)
    project = store.create_project("Durable", "ru")
    character = Character(name="Narrator", voice="aleksandr")
    project = store.add_character(project.id, character)
    scene = Scene(title="Intro", ambience="room_tone")
    project = store.add_scene(project.id, scene)
    store.add_line(project.id, scene.id, DialogueLine(speaker_id=character.id, text="Тест durable jobs."))

    render_service = RenderService(store, tts_provider=FixedTTSProvider(), sfx_provider=None)
    queue = RenderQueue(store, render_service=render_service, max_workers=1)
    job = queue.submit(project.id)

    deadline = time.time() + 10
    while time.time() < deadline:
        current = queue.get_job(job.id)
        if current.status == "done":
            break
        time.sleep(0.05)

    current = queue.get_job(job.id)
    assert current.status == "done"
    assert current.artifact is not None

    reopened_queue = RenderQueue(store, render_service=render_service, max_workers=1)
    persisted = reopened_queue.get_job(job.id)
    assert persisted.status == "done"
    assert persisted.artifact is not None
    assert persisted.artifact.mp3_path == current.artifact.mp3_path


def test_render_queue_recovers_interrupted_jobs_as_queued(tmp_path):
    db_path = tmp_path / "actvoice.sqlite3"
    store = ProjectStore(tmp_path / "projects", db_path=db_path)
    interrupted = RenderJob(project_id="missing-project", status=RenderStatus.rendering, progress=0.4)

    queue = RenderQueue(store, max_workers=1, auto_resume=False)
    queue.save_job(interrupted)

    recovered_queue = RenderQueue(store, max_workers=1, auto_resume=False)
    recovered = recovered_queue.get_job(interrupted.id)
    assert recovered.status == "queued"
    assert recovered.progress == 0.0
