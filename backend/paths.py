from __future__ import annotations

from pathlib import Path
from orchestrator import skills_dir

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ── AI / LLM module paths ─────────────────────────────────────────────────
AGENTS_CONFIG_PATH  = PROJECT_ROOT / "config" / "agents.json"
LLM_SETTINGS_PATH   = PROJECT_ROOT / "config" / "llm_settings.json"
MONGODB_CONFIG_PATH = PROJECT_ROOT / "config" / "mongodb.json"
NOTIFICATIONS_CONFIG_PATH = PROJECT_ROOT / "config" / "notifications.json"
SKILLS_DIR          = skills_dir()
