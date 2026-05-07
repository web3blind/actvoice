from __future__ import annotations

import os
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from app.auth import AgentAuthStore, AgentRegistrationRequest
from app.mcp_tools import ActVoiceTools
from app.store import ProjectStore


def create_mcp_server(store: Optional[ProjectStore] = None, auth_store: Optional[AgentAuthStore] = None) -> FastMCP:
    """Create the ActVoice MCP server.

    Write/render tools require an ActVoice API key. The key can be supplied either:
    - once as `ACTVOICE_API_KEY` in the MCP server environment, or
    - per tool call via the optional `api_key` parameter.

    The per-call parameter is useful for early testing, but production deployments should
    prefer env/header based secret injection by the MCP client instead of putting keys in
    natural-language prompts.
    """

    tools = ActVoiceTools(store or ProjectStore())
    auth = auth_store or AgentAuthStore()
    mcp = FastMCP(
        "ActVoice",
        instructions=(
            "Accessible-first audio drama production studio. Create projects, characters, "
            "scenes, semantic sound cues, and render final MP3 artifacts. The server does "
            "not include an LLM; external agents direct the production through tools."
        ),
    )

    def require_key(api_key: str | None = None) -> None:
        candidate = api_key or os.getenv("ACTVOICE_API_KEY")
        if os.getenv("ACTVOICE_MCP_ALLOW_UNAUTH") == "1":
            return
        if not candidate or not auth.verify(candidate):
            raise PermissionError(
                "ActVoice API key required. Call register_agent first or set ACTVOICE_API_KEY."
            )

    @mcp.tool()
    def register_agent(
        agent_name: str,
        purpose: str | None = None,
        registration_code: str | None = None,
    ) -> dict[str, Any]:
        """Register an MCP client/agent and receive a one-time ActVoice API key."""

        response = auth.register(
            AgentRegistrationRequest(
                agent_name=agent_name,
                purpose=purpose,
                registration_code=registration_code,
            )
        )
        return _dump(response)

    @mcp.tool()
    def list_voices() -> list[dict[str, Any]]:
        """List installed TTS voices exposed by the server."""

        return tools.list_voices()

    @mcp.tool()
    def create_audio_drama_project(
        title: str,
        language: str = "ru",
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Create a new audio drama project. Requires API key."""

        require_key(api_key)
        return tools.create_audio_drama_project(title=title, language=language)

    @mcp.tool()
    def add_character(
        project_id: str,
        name: str,
        voice: str = "aleksandr",
        gender_hint: str | None = None,
        provider: str = "rhvoice",
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Add a character and voice assignment to a project. Requires API key."""

        require_key(api_key)
        return tools.add_character(
            project_id=project_id,
            name=name,
            voice=voice,
            gender_hint=gender_hint,
            provider=provider,
        )

    @mcp.tool()
    def add_scene(
        project_id: str,
        title: str,
        ambience: str | None = "room_tone",
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Add a scene with a semantic ambience type. Requires API key."""

        require_key(api_key)
        return tools.add_scene(project_id=project_id, title=title, ambience=ambience)

    @mcp.tool()
    def add_dialogue_line(
        project_id: str,
        scene_id: str,
        speaker_id: str,
        text: str,
        pause_after_ms: int = 500,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Add a spoken line to a scene. Requires API key."""

        require_key(api_key)
        return tools.add_dialogue_line(
            project_id=project_id,
            scene_id=scene_id,
            speaker_id=speaker_id,
            text=text,
            pause_after_ms=pause_after_ms,
        )

    @mcp.tool()
    def add_sound_cue(
        project_id: str,
        scene_id: str,
        cue_type: str,
        start_ms: int = 0,
        duration_ms: int = 1000,
        level: float = 0.25,
        attributes: dict[str, Any] | None = None,
        anchor: dict[str, Any] | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Add a semantic sound cue. Use anchor for production timing relative to scene/line boundaries."""

        require_key(api_key)
        return tools.add_sound_cue(
            project_id=project_id,
            scene_id=scene_id,
            cue_type=cue_type,
            start_ms=start_ms,
            duration_ms=duration_ms,
            level=level,
            attributes=attributes,
            anchor=anchor,
        )

    @mcp.tool()
    def render_final_mix(project_id: str, api_key: str | None = None) -> dict[str, Any]:
        """Render final MP3/WAV artifacts for a project. Requires API key."""

        require_key(api_key)
        return tools.render_final_mix(project_id=project_id)

    @mcp.tool()
    def get_render_status(job_id: str) -> dict[str, Any]:
        """Get render job status."""

        return tools.get_render_status(job_id=job_id)

    @mcp.tool()
    def get_final_artifact(project_id: str) -> dict[str, Any]:
        """Get the final artifact metadata for a project, if rendered."""

        return tools.get_final_artifact(project_id=project_id)

    return mcp


def _dump(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


if __name__ == "__main__":
    transport = os.getenv("ACTVOICE_MCP_TRANSPORT", "stdio")
    create_mcp_server().run(transport=transport)  # stdio, sse, or streamable-http
