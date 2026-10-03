"""All settings come from environment variables (.env locally, dashboard in production)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(ROOT_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_LLM_MODEL = os.getenv("GROQ_LLM_MODEL", "llama-3.3-70b-versatile")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")

GEMINI_RPM = _int("GEMINI_RPM", 8)
GROQ_RPM = _int("GROQ_RPM", 20)
MAX_LLM_CALLS_PER_SESSION = _int("MAX_LLM_CALLS_PER_SESSION", 12)
MAX_STT_CALLS_PER_SESSION = _int("MAX_STT_CALLS_PER_SESSION", 10)

MAX_CLARIFY_ROUNDS = 2
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_TRANSCRIPT_CHARS = 6000

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

SCHEMA_DIR = BASE_DIR / "schemas"
FONT_DIR = BASE_DIR / "fonts"
DEMO_FILE = BASE_DIR / "demo" / "demo.json"
CACHE_FILE = BASE_DIR / "cache.json"
