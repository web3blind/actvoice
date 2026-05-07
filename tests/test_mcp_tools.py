from __future__ import annotations

from app.mcp_tools import ActVoiceTools
from app.store import ProjectStore


def test_mcp_tools_share_project_service(tmp_path):
    tools = ActVoiceTools(ProjectStore(tmp_path))
    project = tools.create_audio_drama_project("Agent Demo", "ru")
    project_id = project["id"]

    updated = tools.add_character(project_id, name="Narrator", voice="aleksandr")
    character_id = updated["characters"][0]["id"]

    updated = tools.add_scene(project_id, title="Opening", ambience="room_tone")
    scene_id = updated["scenes"][0]["id"]

    updated = tools.add_dialogue_line(project_id, scene_id, character_id, "Привет от агента.")
    updated = tools.add_sound_cue(project_id, scene_id, "notification", start_ms=100)

    assert updated["scenes"][0]["lines"][0]["text"] == "Привет от агента."
    assert updated["scenes"][0]["cues"][0]["type"] == "notification"
