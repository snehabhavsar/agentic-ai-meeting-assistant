import os


class Config:
    """
    Minimal config for prototype.

    Switching SQLite -> Postgres:
    - set DATABASE_URL, e.g.
      postgresql+psycopg://user:pass@localhost:5432/meeting_ai
    """

    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    # DB
    DATABASE_URL = os.environ.get("DATABASE_URL")
    # DB URI is finalized in the Flask app factory so we can safely base SQLite
    # on the resolved `instance_path` (reliable even if cwd changes).
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or ""
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads / generated artifacts
    _BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    _REPO_ROOT = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))

    DATA_DIR = os.environ.get("DATA_DIR", os.path.join(_REPO_ROOT, "data"))
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))
    ARTIFACTS_DIR = os.environ.get("ARTIFACTS_DIR", os.path.join(DATA_DIR, "artifacts"))

    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 200 * 1024 * 1024))  # 200MB

    # Session / auth
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30  # 30 days

    # Lightweight ASR via whisper.cpp (CLI)
    # Example:
    #   export WHISPER_CPP_MODEL="/path/to/ggml-small.bin"
    #   export WHISPER_CPP_BIN="whisper-cli"
    WHISPER_CPP_BIN = os.environ.get("WHISPER_CPP_BIN")  # optional; auto-detected if not set
    WHISPER_CPP_MODEL = os.environ.get("WHISPER_CPP_MODEL")  # required to enable whisper.cpp ASR
    WHISPER_CPP_LANG = os.environ.get("WHISPER_CPP_LANG")  # optional (e.g., "en", "hi")

    # Optional: Deepgram (cloud ASR) + Gemini (cloud summarization), like SMART_MEET_AI reference
    DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
    DEEPGRAM_LANG = os.environ.get("DEEPGRAM_LANG", "en")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
