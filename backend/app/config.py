import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(BACKEND_DIR / 'spendgpt.db').as_posix()}"

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174").split(",")