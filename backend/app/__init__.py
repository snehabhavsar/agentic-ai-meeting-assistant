import os
from urllib.parse import unquote, urlparse

from flask import Flask
from flask_cors import CORS
from sqlalchemy import text

from .config import Config
from .db import db
from typing import Optional, Type


def create_app(config_object: Optional[Type[Config]] = None) -> Flask:    
    """
    Flask app factory.

    Why app factory?
    - Easier testing
    - Cleaner separation of concerns
    - Allows different configs (dev/test/prod)
    """
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    instance_path = os.path.join(backend_dir, "instance")

    # Pin instance_path so SQLite location is deterministic (backend/instance/*).
    app = Flask(__name__, instance_relative_config=True, instance_path=instance_path)
    CORS(app)  # simple cross-origin support for local React dev server

    # Ensure instance folder exists (SQLite file lives here by default).
    os.makedirs(app.instance_path, exist_ok=True)

    config_object = config_object or Config
    app.config.from_object(config_object)

    # Finalize DB URI after instance_path is known.
    # - If DATABASE_URL is set, we use it (e.g., Postgres)
    # - Else we default to SQLite file inside backend/instance/
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        sqlite_file = os.path.join(app.instance_path, "meeting_ai.sqlite")
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{sqlite_file}"

    # If using a SQLite file path (including via DATABASE_URL), ensure the parent
    # directory exists so sqlite can create/open the DB.
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "") or ""
    if uri.startswith("sqlite:") and ":memory:" not in uri:
        parsed = urlparse(uri)
        db_path = unquote(parsed.path or "")

        # Example forms:
        # - sqlite:////abs/path/to.db  -> parsed.path = /abs/path/to.db
        # - sqlite:///relative.db      -> parsed.path = /relative.db (relative to cwd)
        # We make relative paths resolve under backend/ for determinism.
        if db_path.startswith("/") and not os.path.isabs(db_path):
            # defensive; os.path.isabs("/") is True, so this rarely triggers
            db_path = os.path.join(backend_dir, db_path.lstrip("/"))

        if db_path and os.path.isabs(db_path):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        elif db_path:
            os.makedirs(os.path.dirname(os.path.join(backend_dir, db_path.lstrip("/"))), exist_ok=True)

    db.init_app(app)

    # Register blueprints (API routes)
    from .routes.ui import bp as ui_bp
    from .routes.projects import bp as projects_bp
    from .routes.meetings import bp as meetings_bp
    from .routes.action_items import bp as action_items_bp
    from .routes.misc import bp as misc_bp

    app.register_blueprint(ui_bp)
    app.register_blueprint(projects_bp, url_prefix="/api")
    app.register_blueprint(meetings_bp, url_prefix="/api")
    app.register_blueprint(action_items_bp, url_prefix="/api")
    app.register_blueprint(misc_bp, url_prefix="/api")

    # Create tables automatically for prototype usage.
    # In later phases, we can add Flask-Migrate for migrations.
    with app.app_context():
        db.create_all()

        # Prototype "auto-migration" for SQLite: add new columns if missing.
        # This avoids asking you to delete instance DB during demos.
        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "") or ""
        if uri.startswith("sqlite:"):
            # projects.participants_json
            cols = db.session.execute(text("PRAGMA table_info(projects)")).all()
            col_names = {c[1] for c in cols}  # second column is name
            if "participants_json" not in col_names:
                db.session.execute(text("ALTER TABLE projects ADD COLUMN participants_json TEXT"))

            # transcripts.speaker_segments_json
            cols = db.session.execute(text("PRAGMA table_info(transcripts)")).all()
            col_names = {c[1] for c in cols}
            if "speaker_segments_json" not in col_names:
                db.session.execute(text("ALTER TABLE transcripts ADD COLUMN speaker_segments_json TEXT"))

            # meetings processing tracking
            cols = db.session.execute(text("PRAGMA table_info(meetings)")).all()
            col_names = {c[1] for c in cols}
            if "processing_stage" not in col_names:
                db.session.execute(text("ALTER TABLE meetings ADD COLUMN processing_stage TEXT"))
            if "processing_progress" not in col_names:
                db.session.execute(text("ALTER TABLE meetings ADD COLUMN processing_progress INTEGER"))
            if "processing_started_at" not in col_names:
                db.session.execute(text("ALTER TABLE meetings ADD COLUMN processing_started_at DATETIME"))
            if "processing_finished_at" not in col_names:
                db.session.execute(text("ALTER TABLE meetings ADD COLUMN processing_finished_at DATETIME"))

            # action_items.last_rementioned_meeting_id (carry-forward / not done on time)
            cols = db.session.execute(text("PRAGMA table_info(action_items)")).fetchall()
            col_names = {c[1] for c in cols}
            if "last_rementioned_meeting_id" not in col_names:
                db.session.execute(text("ALTER TABLE action_items ADD COLUMN last_rementioned_meeting_id INTEGER"))

            # projects.archived
            cols = db.session.execute(text("PRAGMA table_info(projects)")).fetchall()
            col_names = {c[1] for c in cols}
            if "archived" not in col_names:
                db.session.execute(text("ALTER TABLE projects ADD COLUMN archived INTEGER DEFAULT 0"))
            if "name_aliases_json" not in col_names:
                db.session.execute(text("ALTER TABLE projects ADD COLUMN name_aliases_json TEXT"))

            # meetings.notes
            cols = db.session.execute(text("PRAGMA table_info(meetings)")).fetchall()
            col_names = {c[1] for c in cols}
            if "notes" not in col_names:
                db.session.execute(text("ALTER TABLE meetings ADD COLUMN notes TEXT"))

            db.session.commit()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app

