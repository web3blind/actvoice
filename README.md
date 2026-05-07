# ActVoice

Accessible-first audio drama production service for humans and AI agents.

Domain target: `actvoice.xyz`

ActVoice is designed as a server-side audio drama studio:

- humans use a web/API interface;
- AI agents use MCP/API tools;
- the server stores project manifests;
- the server renders voices, ambience, cues, and final MP3 artifacts;
- no built-in LLM dependency is required for the MVP.

## MVP Modes

TTS provider modes planned:

1. `rhvoice` — free/local/server-side, queued.
2. `openai_byo_key` — future user-provided OpenAI key, fast/paid by user.
3. `edge` — future experimental/fallback mode.

Current implementation includes `RHVoiceProvider`, SQLite-backed project/agent/job storage, in-process `RenderQueue`, Openverse CC0 SFX lookup, timing anchors, and downloadable artifact endpoints.

## Requirements

Ubuntu packages:

```bash
apt-get install -y rhvoice rhvoice-russian rhvoice-english ffmpeg
```

Python:

```bash
python3 -m pip install -e .[dev]
```

## Run API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

With aaPanel Python Manager, configure the same command as the managed Python app/start command. aaPanel can replace a separate `systemd` service for process supervision if it is configured for auto-start after reboot, restart on crash, environment variables, and log access.

Runtime data is stored under `data/` by default:

- `data/actvoice.sqlite3` — SQLite database for projects, render jobs, and agent key hashes.
- `data/projects/PROJECT_ID/` — rendered WAV/MP3/manifest artifacts and caches.

Back up both the SQLite file and `data/projects/`.

## Run MCP Server

Stdio MCP server for local clients such as Hermes:

```bash
python -m app.mcp_server
```

Hermes config example:

```yaml
mcp_servers:
  actvoice:
    command: "python"
    args: ["-m", "app.mcp_server"]
    env:
      ACTVOICE_API_KEY: "[REDACTED]"
```

Run from the project directory or set `PYTHONPATH` to the repo root. The MCP server exposes the same service layer as the REST API.

HTTP/streamable transport is available for later deployment:

```bash
ACTVOICE_MCP_TRANSPORT=streamable-http python -m app.mcp_server
```

For MVP, write tools still require an ActVoice key, either through `ACTVOICE_API_KEY` or an `api_key` tool argument.

## Agent Registration / Minimal Anti-Spam

ActVoice does not implement full login/password auth in the MVP. Instead, agents register and receive a bearer key.

Optional invite protection:

```bash
export ACTVOICE_REGISTRATION_CODE='change-me'
```

Register an agent:

```bash
curl -X POST http://localhost:8080/api/agents/register \
  -H 'content-type: application/json' \
  -d '{"agent_name":"Hermes","purpose":"demo","registration_code":"change-me"}'
```

The response includes an `api_key` once. Write/render endpoints require:

```text
Authorization: Bearer [REDACTED]
```

This is intentionally simpler than full MCP/OAuth auth, but prevents casual write/render spam by just knowing the endpoint.

## Basic API Flow

```bash
ACTVOICE_KEY='paste-the-registration-response-key-here'

curl -X POST http://localhost:8080/api/projects \
  -H "authorization: Bearer $ACTVOICE_KEY" \
  -H 'content-type: application/json' \
  -d '{"title":"Demo","language":"ru"}'
```

Then add characters, scenes, lines, sound cues, and render.

Render requests are queued and return `202 Accepted` with a durable SQLite-backed job id:

```bash
curl -X POST http://localhost:8080/api/projects/PROJECT_ID/render \
  -H "authorization: Bearer $ACTVOICE_KEY"
```

Poll job status:

```bash
curl http://localhost:8080/api/jobs/JOB_ID
```

When done, fetch metadata and files:

```text
GET /api/projects/PROJECT_ID/artifact
GET /api/projects/PROJECT_ID/artifact.mp3
GET /api/projects/PROJECT_ID/artifact.wav
GET /api/projects/PROJECT_ID/render-manifest.json
```

Render jobs are persisted in SQLite. Completed/failed jobs survive aaPanel or process restarts. If a process restarts while a job is `rendering`, ActVoice marks it back to `queued` and can resume it on startup.

## Production Sound Timing

ActVoice does not need a built-in AI to place sounds. External agents or human tools send deterministic timing instructions; the server resolves them during render.

Sound cues can use absolute timing:

```json
{
  "type": "footsteps",
  "start_ms": 31000,
  "duration_ms": 9000,
  "level": 0.2
}
```

Or production-friendly relative anchors:

```json
{
  "type": "laptop_close",
  "duration_ms": 1200,
  "level": 0.45,
  "anchor": {
    "type": "after_line",
    "line_id": "wife_asks_walk",
    "offset_ms": 500
  }
}
```

Supported anchor types:

- `scene_start` with `offset_ms`
- `scene_end` with `offset_ms`
- `before_line` with `line_id` and `offset_ms`
- `after_line` with `line_id` and `offset_ms`

During render, ActVoice measures each generated speech line, writes a `timing_map` into the render manifest, resolves anchors into final `start_ms`, and mixes SFX from those resolved positions. This keeps the core AI-free while letting any MCP agent build sound design from text.

## Development

```bash
python3 -m pytest -q
```

If `pytest` is unavailable, install dev dependencies first.

## Notes

- `data/` is local runtime storage and is gitignored.
- MCP should call the same service layer as REST; do not duplicate business logic.
- Sound cues are semantic (`footsteps`, `water_drip`) instead of raw filenames.
- SFX rendering prefers Openverse CC0 audio for known cue types (`brook`, `birds`, `footsteps`, `laptop_close`) and falls back to synthetic generation only when search/download fails or no mapping exists.

