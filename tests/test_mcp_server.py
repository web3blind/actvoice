from __future__ import annotations

import asyncio

from app.auth import AgentAuthStore
from app.mcp_server import create_mcp_server
from app.store import ProjectStore


def test_mcp_server_exposes_expected_tools(tmp_path):
    async def run():
        mcp = create_mcp_server(
            ProjectStore(tmp_path / "projects"),
            AgentAuthStore(tmp_path / "agents.json"),
        )
        tools = await mcp.list_tools()
        names = {tool.name for tool in tools}
        assert "register_agent" in names
        assert "create_audio_drama_project" in names
        assert "render_final_mix" in names

    asyncio.run(run())


def test_mcp_write_tool_requires_key_then_accepts_registered_key(tmp_path):
    async def run():
        mcp = create_mcp_server(
            ProjectStore(tmp_path / "projects"),
            AgentAuthStore(tmp_path / "agents.json"),
        )

        try:
            await mcp.call_tool("create_audio_drama_project", {"title": "Denied"})
            raise AssertionError("write tool unexpectedly allowed without key")
        except Exception as exc:
            assert "API key required" in str(exc)

        _content, result = await mcp.call_tool("register_agent", {"agent_name": "Hermes"})
        api_key = result["api_key"]

        _content, project = await mcp.call_tool(
            "create_audio_drama_project",
            {"title": "Allowed", "language": "ru", "api_key": api_key},
        )
        assert project["title"] == "Allowed"

    asyncio.run(run())


def test_mcp_add_sound_cue_accepts_relative_anchor(tmp_path):
    async def run():
        mcp = create_mcp_server(
            ProjectStore(tmp_path / "projects"),
            AgentAuthStore(tmp_path / "agents.json"),
        )
        _content, registration = await mcp.call_tool("register_agent", {"agent_name": "Hermes"})
        api_key = registration["api_key"]
        _content, project = await mcp.call_tool(
            "create_audio_drama_project",
            {"title": "Anchored", "language": "ru", "api_key": api_key},
        )
        _content, project = await mcp.call_tool(
            "add_character",
            {"project_id": project["id"], "name": "Narrator", "voice": "aleksandr", "api_key": api_key},
        )
        character_id = project["characters"][0]["id"]
        _content, project = await mcp.call_tool(
            "add_scene",
            {"project_id": project["id"], "title": "Scene", "ambience": "brook", "api_key": api_key},
        )
        scene_id = project["scenes"][0]["id"]
        _content, project = await mcp.call_tool(
            "add_dialogue_line",
            {
                "project_id": project["id"],
                "scene_id": scene_id,
                "speaker_id": character_id,
                "text": "Пойдём гулять.",
                "api_key": api_key,
            },
        )
        line_id = project["scenes"][0]["lines"][0]["id"]
        _content, project = await mcp.call_tool(
            "add_sound_cue",
            {
                "project_id": project["id"],
                "scene_id": scene_id,
                "cue_type": "footsteps",
                "duration_ms": 4000,
                "level": 0.2,
                "anchor": {"type": "after_line", "line_id": line_id, "offset_ms": 300},
                "api_key": api_key,
            },
        )

        cue = project["scenes"][0]["cues"][0]
        assert cue["anchor"] == {"type": "after_line", "line_id": line_id, "offset_ms": 300}

    asyncio.run(run())
