from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app.auth import AgentAuthStore, AgentRegistrationRequest
from app.models import Character, DialogueLine, Scene, SoundCue
from app.render import RenderService
from app.render_queue import RenderQueue
from app.store import ProjectNotFound, ProjectStore
from app.tts import RHVoiceProvider, default_tts_provider


def dump_model(model):
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


app = FastAPI(title="ActVoice", version="0.1.0")
store = ProjectStore()
render_service = RenderService(store)
render_queue = RenderQueue(store, render_service=render_service)
auth_store = AgentAuthStore()


HOME_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ActVoice — accessible audio drama studio</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #050507; color: #f4f4f5; line-height: 1.6; }
    main { max-width: 58rem; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
    a { color: #00d992; }
    code, pre { background: #151518; color: #f8fafc; border-radius: .5rem; }
    code { padding: .1rem .3rem; }
    pre { padding: 1rem; overflow-x: auto; }
    .copy-snippet { margin: 1rem 0; }
    .copy-snippet-header { display: flex; gap: .75rem; align-items: center; justify-content: space-between; flex-wrap: wrap; margin-bottom: .35rem; }
    .copy-snippet-title { font-weight: 700; }
    .copy-button, .language-button { border: 1px solid #00d992; border-radius: .5rem; background: #04100c; color: #f4f4f5; cursor: pointer; padding: .4rem .7rem; }
    .copy-button:focus-visible, .language-button:focus-visible { outline: 3px solid #d4a843; outline-offset: 2px; }
    .language-button[aria-pressed="true"] { background: #00d992; color: #04100c; }
    .copy-status { color: #d4a843; min-height: 1.5em; }
    .tagline { font-size: 1.2rem; color: #d4a843; }
    .card { border: 1px solid #2f2f36; border-radius: 1rem; padding: 1rem; margin: 1rem 0; background: #0d0d11; }
    .skip-link { position: absolute; left: .5rem; top: .5rem; background: #00d992; color: #04100c; padding: .5rem; }
    .language-switcher { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; margin: 1rem 0; }
    [data-language-panel][hidden] { display: none; }
  </style>
</head>
<body>
<a class="skip-link" href="#start">Skip to instructions / Перейти к инструкции</a>
<main>
  <nav class="language-switcher" aria-label="Language / Язык">
    <span id="language-switcher-label">Language / Язык:</span>
    <button class="language-button" type="button" data-set-language="en" aria-pressed="true">English</button>
    <button class="language-button" type="button" data-set-language="ru" aria-pressed="false">Русский</button>
  </nav>

  <div data-language-panel="en">
    <header>
      <h1>ActVoice</h1>
      <p class="tagline">Audio drama studio for humans and AI agents.</p>
      <p>ActVoice turns a text project manifest into a rendered audio drama: characters, voices, scenes, dialogue, ambience, sound cues, and a final MP3 artifact.</p>
    </header>

    <section class="card" aria-labelledby="accessibility-en">
      <h2 id="accessibility-en">Screen-reader friendly workflow</h2>
      <p><strong>No visual timeline required.</strong> The core workflow is text-first: create a project, add characters, add scenes, add dialogue lines, add semantic sound cues, then render.</p>
      <p>Everything important is available through REST API and MCP tools, so a blind creator can work through a screen reader, terminal, or AI agent.</p>
    </section>

    <section id="start" class="card" aria-labelledby="quickstart-en">
      <h2 id="quickstart-en">Quick start for agents</h2>
      <ol>
        <li><strong>Register an agent.</strong> Call <code>POST /api/agents/register</code> and receive an ActVoice API key.</li>
        <li><strong>Connect with MCP.</strong> Local clients can run <code>python -m app.mcp_server</code>. Future remote clients will connect to <code>https://actvoice.xyz/mcp</code>.</li>
        <li><strong>Create a project.</strong> Use MCP tool <code>create_audio_drama_project</code> or REST endpoint <code>POST /api/projects</code>.</li>
        <li><strong>Build the script.</strong> Add characters, scenes, dialogue lines, and semantic sound cues like <code>footsteps</code>, <code>brook</code>, <code>birds</code>, or <code>laptop_close</code>.</li>
        <li><strong>Place sounds with timing anchors.</strong> Agents can use absolute <code>start_ms</code> or relative anchors such as <code>after_line</code> plus <code>line_id</code> and <code>offset_ms</code>. ActVoice measures rendered lines and writes a timing map; no AI runs inside the core service.</li>
        <li><strong>Render.</strong> Call <code>render_final_mix</code> or <code>POST /api/projects/{project_id}/render</code>. REST rendering is queued and returns a job id; poll <code>GET /api/jobs/{job_id}</code>.</li>
        <li><strong>Download artifacts.</strong> When the job is done, fetch metadata or files from <code>/api/projects/{project_id}/artifact</code>, <code>/artifact.mp3</code>, <code>/artifact.wav</code>, or <code>/render-manifest.json</code>.</li>
      </ol>
    </section>

    <section class="card" aria-labelledby="copy-ready-examples-en">
      <h2 id="copy-ready-examples-en">Copy-ready examples</h2>
      <p>Each example is a real command or request shape. Replace placeholders such as <code>[API_KEY]</code>, <code>[PROJECT_ID]</code>, and <code>[JOB_ID]</code> before running.</p>

      <div class="copy-snippet">
        <div class="copy-snippet-header">
          <span class="copy-snippet-title">Register an agent</span>
          <button class="copy-button" type="button" data-copy-target="snippet-register-en" aria-describedby="copy-status-en">Copy</button>
        </div>
        <pre><code id="snippet-register-en">curl -X POST https://actvoice.xyz/api/agents/register \
  -H 'Content-Type: application/json' \
  -d '{"agent_name":"Hermes","purpose":"audio drama render"}'</code></pre>
      </div>

      <div class="copy-snippet">
        <div class="copy-snippet-header">
          <span class="copy-snippet-title">Create a project</span>
          <button class="copy-button" type="button" data-copy-target="snippet-create-project-en" aria-describedby="copy-status-en">Copy</button>
        </div>
        <pre><code id="snippet-create-project-en">curl -X POST https://actvoice.xyz/api/projects \
  -H 'Authorization: Bearer [API_KEY]' \
  -H 'Content-Type: application/json' \
  -d '{"title":"My audio drama","language":"ru"}'</code></pre>
      </div>

      <div class="copy-snippet">
        <div class="copy-snippet-header">
          <span class="copy-snippet-title">Render and download</span>
          <button class="copy-button" type="button" data-copy-target="snippet-render-download-en" aria-describedby="copy-status-en">Copy</button>
        </div>
        <pre><code id="snippet-render-download-en">curl -X POST https://actvoice.xyz/api/projects/[PROJECT_ID]/render \
  -H 'Authorization: Bearer [API_KEY]'

curl https://actvoice.xyz/api/jobs/[JOB_ID]
curl -L -o final_mix.mp3 https://actvoice.xyz/api/projects/[PROJECT_ID]/artifact.mp3</code></pre>
      </div>

      <div class="copy-snippet">
        <div class="copy-snippet-header">
          <span class="copy-snippet-title">Local MCP server</span>
          <button class="copy-button" type="button" data-copy-target="snippet-mcp-en" aria-describedby="copy-status-en">Copy</button>
        </div>
        <pre><code id="snippet-mcp-en">ACTVOICE_API_KEY='[API_KEY]' python -m app.mcp_server</code></pre>
      </div>
      <p id="copy-status-en" class="copy-status" role="status" aria-live="polite"></p>
    </section>

    <section class="card" aria-labelledby="auth-en">
      <h2 id="auth-en">Authentication</h2>
      <p>Write and render actions require a bearer key:</p>
      <pre><code>Authorization: Bearer [API_KEY]</code></pre>
      <p>For local stdio MCP, the same key can be provided as <code>ACTVOICE_API_KEY</code>. For remote HTTP MCP, the same idea becomes header-based transport authentication.</p>
    </section>

    <section class="card" aria-labelledby="tts-en">
      <h2 id="tts-en">Voice and rendering modes</h2>
      <ul>
        <li><code>edge</code>: current free/default neural voice mode.</li>
        <li><code>rhvoice</code>: local/offline fallback if Edge is unavailable or explicitly requested.</li>
        <li><code>openai_byo_key</code>: planned user-provided paid provider mode.</li>
      </ul>
    </section>

    <section class="card" aria-labelledby="project-links-en">
      <h2 id="project-links-en">Project links</h2>
      <ul>
        <li><a href="https://x.com/denis_skripnik" rel="me noopener noreferrer">Author on X</a></li>
        <li><a href="https://github.com/web3blind/actvoice" rel="noopener noreferrer">Source on GitHub</a></li>
      </ul>
    </section>

    <section class="card" aria-labelledby="status-en">
      <h2 id="status-en">Service endpoints</h2>
      <ul>
        <li>Health: <a href="/health"><code>/health</code></a></li>
        <li>Voices: <a href="/api/voices"><code>/api/voices</code></a></li>
        <li>OpenAPI schema: <a href="/docs"><code>/docs</code></a></li>
      </ul>
    </section>
  </div>

  <div data-language-panel="ru" hidden>
    <header>
      <h1>ActVoice</h1>
      <p class="tagline">Студия аудиоспектаклей для людей и AI-агентов.</p>
      <p>ActVoice превращает текстовый манифест проекта в готовый аудиоспектакль: персонажи, голоса, сцены, реплики, атмосфера, звуковые события и финальный MP3-файл.</p>
    </header>

    <section class="card" aria-labelledby="accessibility-ru">
      <h2 id="accessibility-ru">Удобный workflow для скринридера</h2>
      <p><strong>Визуальная таймлиния не нужна.</strong> Основной процесс текстовый: создать проект, добавить персонажей, сцены, реплики, смысловые звуковые события и запустить рендер.</p>
      <p>Всё важное доступно через REST API и MCP tools, поэтому незрячий автор может работать через скринридер, терминал или AI-агента.</p>
    </section>

    <section class="card" aria-labelledby="quickstart-ru">
      <h2 id="quickstart-ru">Быстрый старт для агентов</h2>
      <ol>
        <li><strong>Зарегистрируйте агента.</strong> Вызовите <code>POST /api/agents/register</code> и получите API-ключ ActVoice.</li>
        <li><strong>Подключитесь через MCP.</strong> Локально можно запустить <code>python -m app.mcp_server</code>. В будущем remote-клиенты смогут подключаться к <code>https://actvoice.xyz/mcp</code>.</li>
        <li><strong>Создайте проект.</strong> Используйте MCP tool <code>create_audio_drama_project</code> или REST endpoint <code>POST /api/projects</code>.</li>
        <li><strong>Соберите сценарий.</strong> Добавьте персонажей, сцены, реплики и смысловые звуковые события: <code>footsteps</code>, <code>brook</code>, <code>birds</code>, <code>laptop_close</code>.</li>
        <li><strong>Расставьте звуки по времени.</strong> Агенты могут использовать точный <code>start_ms</code> или относительные anchors: <code>after_line</code> плюс <code>line_id</code> и <code>offset_ms</code>. ActVoice измеряет длительность озвученных реплик и пишет timing map; внутри core-сервиса AI не запускается.</li>
        <li><strong>Запустите рендер.</strong> Вызовите <code>render_final_mix</code> или <code>POST /api/projects/{project_id}/render</code>. REST-рендер ставится в очередь и возвращает job id; статус проверяется через <code>GET /api/jobs/{job_id}</code>.</li>
        <li><strong>Скачайте артефакты.</strong> Когда job завершён, заберите metadata или файлы из <code>/api/projects/{project_id}/artifact</code>, <code>/artifact.mp3</code>, <code>/artifact.wav</code> или <code>/render-manifest.json</code>.</li>
      </ol>
    </section>

    <section class="card" aria-labelledby="copy-ready-examples-ru">
      <h2 id="copy-ready-examples-ru">Готовые примеры для копирования</h2>
      <p>Каждый пример — настоящая команда или форма запроса. Перед запуском замените placeholders <code>[API_KEY]</code>, <code>[PROJECT_ID]</code> и <code>[JOB_ID]</code>.</p>

      <div class="copy-snippet">
        <div class="copy-snippet-header">
          <span class="copy-snippet-title">Зарегистрировать агента</span>
          <button class="copy-button" type="button" data-copy-target="snippet-register-ru" aria-describedby="copy-status-ru">Копировать</button>
        </div>
        <pre><code id="snippet-register-ru">curl -X POST https://actvoice.xyz/api/agents/register \
  -H 'Content-Type: application/json' \
  -d '{"agent_name":"Hermes","purpose":"audio drama render"}'</code></pre>
      </div>

      <div class="copy-snippet">
        <div class="copy-snippet-header">
          <span class="copy-snippet-title">Создать проект</span>
          <button class="copy-button" type="button" data-copy-target="snippet-create-project-ru" aria-describedby="copy-status-ru">Копировать</button>
        </div>
        <pre><code id="snippet-create-project-ru">curl -X POST https://actvoice.xyz/api/projects \
  -H 'Authorization: Bearer [API_KEY]' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Мой аудиоспектакль","language":"ru"}'</code></pre>
      </div>

      <div class="copy-snippet">
        <div class="copy-snippet-header">
          <span class="copy-snippet-title">Запустить рендер и скачать MP3</span>
          <button class="copy-button" type="button" data-copy-target="snippet-render-download-ru" aria-describedby="copy-status-ru">Копировать</button>
        </div>
        <pre><code id="snippet-render-download-ru">curl -X POST https://actvoice.xyz/api/projects/[PROJECT_ID]/render \
  -H 'Authorization: Bearer [API_KEY]'

curl https://actvoice.xyz/api/jobs/[JOB_ID]
curl -L -o final_mix.mp3 https://actvoice.xyz/api/projects/[PROJECT_ID]/artifact.mp3</code></pre>
      </div>

      <div class="copy-snippet">
        <div class="copy-snippet-header">
          <span class="copy-snippet-title">Локальный MCP server</span>
          <button class="copy-button" type="button" data-copy-target="snippet-mcp-ru" aria-describedby="copy-status-ru">Копировать</button>
        </div>
        <pre><code id="snippet-mcp-ru">ACTVOICE_API_KEY='[API_KEY]' python -m app.mcp_server</code></pre>
      </div>
      <p id="copy-status-ru" class="copy-status" role="status" aria-live="polite"></p>
    </section>

    <section class="card" aria-labelledby="auth-ru">
      <h2 id="auth-ru">Аутентификация</h2>
      <p>Действия записи и рендера требуют bearer key:</p>
      <pre><code>Authorization: Bearer [API_KEY]</code></pre>
      <p>Для локального stdio MCP тот же ключ можно передать как <code>ACTVOICE_API_KEY</code>. Для remote HTTP MCP используется та же идея, но через header-based transport authentication.</p>
    </section>

    <section class="card" aria-labelledby="tts-ru">
      <h2 id="tts-ru">Голоса и режимы рендера</h2>
      <ul>
        <li><code>edge</code>: текущий бесплатный/default режим нейронных голосов.</li>
        <li><code>rhvoice</code>: локальный/offline fallback, если Edge недоступен или выбран явно.</li>
        <li><code>openai_byo_key</code>: планируемый режим платного провайдера с ключом пользователя.</li>
      </ul>
    </section>

    <section class="card" aria-labelledby="project-links-ru">
      <h2 id="project-links-ru">Ссылки проекта</h2>
      <ul>
        <li><a href="https://x.com/denis_skripnik" rel="me noopener noreferrer">Автор в X</a></li>
        <li><a href="https://github.com/web3blind/actvoice" rel="noopener noreferrer">Исходный код на GitHub</a></li>
      </ul>
    </section>

    <section class="card" aria-labelledby="status-ru">
      <h2 id="status-ru">Service endpoints</h2>
      <ul>
        <li>Health: <a href="/health"><code>/health</code></a></li>
        <li>Voices: <a href="/api/voices"><code>/api/voices</code></a></li>
        <li>OpenAPI schema: <a href="/docs"><code>/docs</code></a></li>
      </ul>
    </section>
  </div>
</main>
<script>
  const messages = {
    en: {
      copied: 'Copied to clipboard.',
      failed: 'Copy failed. Select the code block and copy it manually.'
    },
    ru: {
      copied: 'Скопировано в буфер обмена.',
      failed: 'Не удалось скопировать. Выделите блок кода и скопируйте вручную.'
    }
  };

  function preferredLanguage() {
    const saved = window.localStorage.getItem('actvoice-language');
    if (saved === 'ru' || saved === 'en') return saved;
    const browserLanguage = (navigator.language || navigator.userLanguage || 'en').toLowerCase();
    return browserLanguage.startsWith('ru') ? 'ru' : 'en';
  }

  function applyLanguage(language) {
    const selected = language === 'ru' ? 'ru' : 'en';
    document.documentElement.lang = selected;
    document.querySelectorAll('[data-language-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.languagePanel !== selected;
    });
    document.querySelectorAll('[data-set-language]').forEach((button) => {
      button.setAttribute('aria-pressed', button.dataset.setLanguage === selected ? 'true' : 'false');
    });
  }

  async function copySnippet(targetId, statusEl) {
    const target = document.getElementById(targetId);
    if (!target || !statusEl) return;
    const text = target.innerText;
    const language = document.documentElement.lang === 'ru' ? 'ru' : 'en';
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.setAttribute('readonly', '');
        textarea.style.position = 'absolute';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      statusEl.textContent = messages[language].copied;
    } catch (error) {
      statusEl.textContent = messages[language].failed;
    }
  }

  document.querySelectorAll('[data-set-language]').forEach((button) => {
    button.addEventListener('click', () => {
      const language = button.dataset.setLanguage;
      window.localStorage.setItem('actvoice-language', language);
      applyLanguage(language);
    });
  });

  document.querySelectorAll('[data-copy-target]').forEach((button) => {
    button.addEventListener('click', () => {
      const statusEl = document.getElementById(button.getAttribute('aria-describedby'));
      copySnippet(button.dataset.copyTarget, statusEl);
    });
  });

  applyLanguage(preferredLanguage());
</script>
</body>
</html>
"""


class CreateProjectRequest(BaseModel):
    title: str
    language: str = "ru"


def require_agent_key(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    api_key = authorization.split(" ", 1)[1].strip()
    if not auth_store.verify(api_key):
        raise HTTPException(status_code=403, detail="invalid bearer token")


@app.get("/", response_class=HTMLResponse)
def homepage() -> str:
    return HOME_HTML


@app.post("/api/agents/register")
def register_agent(request: AgentRegistrationRequest) -> dict:
    try:
        return dump_model(auth_store.register(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict:
    rhvoice = RHVoiceProvider()
    tts = default_tts_provider()
    return {"ok": True, "service": "actvoice", "tts": tts.is_available(), "rhvoice": rhvoice.is_available()}


@app.get("/api/voices")
def list_voices() -> list[dict]:
    return [voice.__dict__ for voice in default_tts_provider().list_voices()]


@app.post("/api/projects", dependencies=[Depends(require_agent_key)])
def create_project(request: CreateProjectRequest) -> dict:
    return dump_model(store.create_project(title=request.title, language=request.language))


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    try:
        return dump_model(store.get(project_id))
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None


@app.post("/api/projects/{project_id}/characters", dependencies=[Depends(require_agent_key)])
def add_character(project_id: str, character: Character) -> dict:
    try:
        return dump_model(store.add_character(project_id, character))
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None


@app.post("/api/projects/{project_id}/scenes", dependencies=[Depends(require_agent_key)])
def add_scene(project_id: str, scene: Scene) -> dict:
    try:
        return dump_model(store.add_scene(project_id, scene))
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None


@app.post("/api/projects/{project_id}/scenes/{scene_id}/lines", dependencies=[Depends(require_agent_key)])
def add_line(project_id: str, scene_id: str, line: DialogueLine) -> dict:
    try:
        return dump_model(store.add_line(project_id, scene_id, line))
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/scenes/{scene_id}/sound-cues", dependencies=[Depends(require_agent_key)])
def add_sound_cue(project_id: str, scene_id: str, cue: SoundCue) -> dict:
    try:
        return dump_model(store.add_sound_cue(project_id, scene_id, cue))
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/render", dependencies=[Depends(require_agent_key)], status_code=202)
def render_project(project_id: str) -> dict:
    try:
        store.get(project_id)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None
    return dump_model(render_queue.submit(project_id))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    try:
        return dump_model(render_queue.get_job(job_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found") from None


def _artifact_path(project_id: str, attribute: str) -> Path:
    try:
        project = store.get(project_id)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None
    raw_path = getattr(project.artifact, attribute)
    if not raw_path:
        raise HTTPException(status_code=404, detail="artifact not rendered")
    path = Path(raw_path).resolve()
    project_root = store.project_dir(project_id).resolve()
    if project_root not in path.parents:
        raise HTTPException(status_code=403, detail="artifact path outside project")
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact file missing")
    return path


@app.get("/api/projects/{project_id}/artifact")
def get_artifact(project_id: str) -> dict:
    try:
        project = store.get(project_id)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None
    if not project.artifact.mp3_path:
        raise HTTPException(status_code=404, detail="artifact not rendered")
    return dump_model(project.artifact)


@app.get("/api/projects/{project_id}/artifact.mp3")
def download_mp3(project_id: str) -> FileResponse:
    path = _artifact_path(project_id, "mp3_path")
    return FileResponse(path, media_type="audio/mpeg", filename=f"actvoice-{project_id}.mp3")


@app.get("/api/projects/{project_id}/artifact.wav")
def download_wav(project_id: str) -> FileResponse:
    path = _artifact_path(project_id, "wav_path")
    return FileResponse(path, media_type="audio/wav", filename=f"actvoice-{project_id}.wav")


@app.get("/api/projects/{project_id}/render-manifest.json")
def download_render_manifest(project_id: str) -> FileResponse:
    path = _artifact_path(project_id, "render_manifest_path")
    return FileResponse(path, media_type="application/json", filename=f"actvoice-{project_id}-manifest.json")
