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
    # Keep SQLite as a simple default for the prototype.
    # Path is relative to backend/ when you run `python run.py` from backend/.
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or "sqlite:///instance/meeting_ai.sqlite"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads / generated artifacts
    _BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    _REPO_ROOT = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))

    DATA_DIR = os.environ.get("DATA_DIR", os.path.join(_REPO_ROOT, "data"))
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))
    ARTIFACTS_DIR = os.environ.get("ARTIFACTS_DIR", os.path.join(DATA_DIR, "artifacts"))

    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 200 * 1024 * 1024))  # 200MB

