from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
SQLITE_DB_PATH = DATA_DIR / "actvoice.sqlite3"
DEFAULT_SAMPLE_RATE = 24_000
