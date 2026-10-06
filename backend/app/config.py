import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STARTER_PACK_DIR = BASE_DIR / "swasthiq-front-desk-agent-starter-pack"
CLINIC_JSON_PATH = os.getenv("CLINIC_JSON_PATH", str(STARTER_PACK_DIR / "clinic.json"))

# Database path (for in-memory or persistent store)
DB_PATH = os.getenv("DB_PATH", ":memory:")
PERSISTENT_DB_PATH = BASE_DIR / "backend" / "clinic_state.db"

# LLM Configurations
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

# Default Reference Date
DEFAULT_TODAY = "2026-10-01"
