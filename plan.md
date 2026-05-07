# ActVoice MVP Plan

Domain: `actvoice.xyz`

## Goal

Build an open-source, accessible-first audio drama production service with:
- REST API for humans/web UI;
- MCP-compatible tool surface for AI agents;
- server-side rendering of audio artifacts;
- RHVoice free/basic TTS mode;
- Openverse CC0 SFX provider for real ambience/foley;
- synthetic ambience/SFX fallback when no real asset is available;
- future provider slots for OpenAI BYO key and Edge/Microsoft.

The service should not depend on a built-in LLM. External agents use MCP/API to create projects and render final MP3 files.

## Non-goals for MVP

- No built-in AI Director yet.
- No username/password user accounts; MVP uses agent registration + bearer keys.
- No payment system yet.
- No large third-party SFX library yet.
- No browser DAW/timeline editor yet.
- No full deployment automation yet; render queue and artifact serving are implemented in-process for hosted MVP.

## Stack

Initial stack:
- Python 3
- FastAPI
- Pydantic
- RHVoice via `RHVoice-test`
- ffmpeg/ffprobe
- SQLite-backed project/agent/render-job storage plus filesystem artifact storage for MVP
- pytest for tests

Rationale: Python is best for server-side audio processing, RHVoice subprocess calls, synthetic audio generation, and quick FastAPI/MCP implementation.

## Architecture

```text
Website / REST API / MCP tools
  -> Project service
  -> SQLite storage (projects + agents + render jobs)
  -> Render queue/service
  -> TTS provider abstraction
      -> RHVoiceProvider
      -> future OpenAITTSProvider
      -> future EdgeTTSProvider
  -> SFX provider abstraction
      -> OpenverseSFXProvider (CC0 real sounds)
      -> Synthetic SFX/Ambience fallback
  -> ffmpeg mixer
  -> artifact storage
```

## Core Concepts

Project:
- id
- title
- language
- characters
- scenes
- render settings
- artifact metadata

Character:
- id
- display name
- role/gender hint
- voice provider
- voice id

Scene:
- id
- title
- ambience
- lines
- sound cues

Line:
- speaker id
- text
- pause_after_ms
- optional rate/pitch/volume

SoundCue:
- semantic type: `footsteps`, `water_drip`, `notification`, `heartbeat`, etc.
- absolute timing: `start_ms`, `duration_ms`, `level`
- production relative timing: optional `anchor` with `type`, optional `line_id`, and `offset_ms`
- supported anchor types: `scene_start`, `scene_end`, `before_line`, `after_line`
- optional attributes: mood, surface, intensity, Openverse query override

## MVP API

Auth:
- `POST /api/agents/register` — issue bearer key for an agent; optional `ACTVOICE_REGISTRATION_CODE` invite gate.

Public endpoints:
- `GET /health`
- `GET /api/voices`
- `GET /api/projects/{project_id}`
- `GET /api/jobs/{job_id}`
- `GET /api/projects/{project_id}/artifact`
- `GET /api/projects/{project_id}/artifact.mp3`
- `GET /api/projects/{project_id}/artifact.wav`
- `GET /api/projects/{project_id}/render-manifest.json`

Write/render endpoints require `Authorization: Bearer [REDACTED]`.

- `POST /api/projects`
- `POST /api/projects/{project_id}/characters`
- `POST /api/projects/{project_id}/scenes`
- `POST /api/projects/{project_id}/scenes/{scene_id}/lines`
- `POST /api/projects/{project_id}/scenes/{scene_id}/sound-cues`
- `POST /api/projects/{project_id}/render` — returns `202 Accepted` queued job metadata.

Render queue:
- implemented as `app/render_queue.py` with configurable `ACTVOICE_RENDER_WORKERS`;
- returns queued jobs immediately instead of blocking HTTP requests;
- persists job status/artifact/error in SQLite, so done/failed jobs survive aaPanel/process restarts;
- marks interrupted `rendering` jobs back to `queued` on startup and can auto-resume pending work;
- stores final artifact metadata on the project;
- can later be swapped for Redis/RQ/Celery without changing the API surface.

MCP transport:
- implemented as `app/mcp_server.py` using the official Python MCP SDK (`FastMCP`);
- default transport is stdio for local clients;
- `ACTVOICE_MCP_TRANSPORT=streamable-http` can expose HTTP transport later;
- write/render MCP tools require ActVoice API key via `ACTVOICE_API_KEY` env or `api_key` argument.

MCP tool functions call the same service layer as REST:
- `create_audio_drama_project`
- `add_character`
- `list_voices`
- `assign_voice`
- `add_scene`
- `add_dialogue_line`
- `add_sound_cue`
- `render_final_mix`
- `get_render_status`
- `get_final_artifact`

## TTS Providers

MVP:
- `RHVoiceProvider`

Future:
- `OpenAITTSProvider` with user-provided key
- `EdgeTTSProvider` as experimental/fallback

Provider abstraction:

```python
synthesize(text, voice, output_path, *, rate=100, pitch=100, volume=100) -> AudioSegmentMetadata
```

## Sound Design Strategy

MVP prefers real CC0 sounds through Openverse:
- semantic cue types map to Openverse queries, e.g. `brook -> brook stream water`, `birds -> forest birds`, `footsteps -> footsteps gravel walking`, `laptop_close -> laptop close`;
- Openverse results are filtered to `license=cc0`;
- downloaded audio is cached under the project build directory;
- long ambience is trimmed to the requested `duration_ms`;
- short one-shots can be looped/truncated by ffmpeg to fit the requested duration;
- render manifests preserve provider/title/creator/license/source/landing URL metadata.

Synthetic generation remains a fallback for unsupported cue types or Openverse/network failures:
- room tone
- wind/noise bed
- tension pad/drone
- heartbeat pulse
- notification/beep
- water drip approximation
- footsteps approximation

Later add a curated local CC0 SFX pack with provenance manifest so common cues do not require network search at render time.

Agents should add semantic cues, not raw filenames. Timing can be controlled either by absolute `start_ms` or by relative anchors such as `after_line` plus `line_id` and `offset_ms`. During render, ActVoice measures generated line durations, writes a `timing_map` into `render_manifest.json`, resolves anchors into final `start_ms`, and mixes cues deterministically without any built-in AI.

## Render Strategy

For each line:
1. synthesize voice to WAV;
2. normalize/convert sample rate;
3. concatenate with pauses into scene dialogue;
4. generate ambience/cues for scene duration;
5. mix scene dialogue + ambience + cues;
6. concatenate scenes;
7. encode final MP3;
8. write render manifest;
9. store artifact URLs for MP3/WAV/manifest download endpoints.

## Storage Layout

```text
actvoice/
  app/
  tests/
  data/
    projects/{project_id}/project.json
    projects/{project_id}/build/
      lines/
      scenes/
      final_mix.wav
      final_mix.mp3
      render_manifest.json
```

`data/` is gitignored.

## Testing Strategy

Unit tests:
- manifest models validate correctly;
- project service creates/mutates projects;
- sound cue generator creates WAV files;
- render queue state transitions;
- RHVoice provider detects availability and can be skipped if missing.

Integration smoke:
- create tiny project;
- render with RHVoice if installed;
- final MP3 exists and ffprobe duration is positive.

## Definition of Done for MVP Scaffold

- `plan.md` exists.
- Python package scaffold exists.
- REST app starts.
- Project CRUD service works.
- RHVoice provider implemented.
- Synthetic SFX generator implemented for basic cues.
- Render service can create a short MP3 from a manifest.
- REST render endpoint queues jobs and exposes job status.
- Artifact endpoints serve MP3/WAV/manifest files by URL.
- Tests pass.
- README explains domain, concept, setup, and API flow.
