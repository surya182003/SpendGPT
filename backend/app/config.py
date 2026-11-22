import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(BACKEND_DIR / 'spendgpt.db').as_posix()}"

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174").split(",")


# --- AI / LM Studio ------------------------------------------------------------
# LM Studio runs a local OpenAI-compatible server (Developer tab -> Start Server,
# or `lms server start`). Only this backend talks to it; the React app never does.
def _env_bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


LM_STUDIO_ENABLED = _env_bool("LM_STUDIO_ENABLED", "true")
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1").rstrip("/")
# Model identifier as shown in LM Studio (e.g. "qwen2.5-7b-instruct").
# Leave empty to use whichever chat model is currently loaded.
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "")
# Only needed if "Require API token" is switched on in LM Studio's server settings.
# Set it in your environment / backend/.env - never commit it.
LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "")
LM_STUDIO_TIMEOUT = float(os.getenv("LM_STUDIO_TIMEOUT", "60"))  # seconds for a full reply
LM_STUDIO_CONNECT_TIMEOUT = float(os.getenv("LM_STUDIO_CONNECT_TIMEOUT", "5"))
