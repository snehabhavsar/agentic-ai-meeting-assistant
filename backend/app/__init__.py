import os
from urllib.parse import unquote, urlparse

from flask import Flask, request, redirect
from flask_cors import CORS
from flask_login import LoginManager
from sqlalchemy import text

from .config import Config
from .db import db
from typing import Optional, Type


def create_app(config_object: Optional[Type[Config]] = None) -> Flask:
    """Flask app factory."""
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    instance_path = os.path.join(backend_dir, "instance")

    app = Flask(__name__, instance_relative_config=True, instance_path=instance_path)
    CORS(app, supports_credentials=True)

    os.makedirs(app.instance_path, exist_ok=True)

    config_object = config_object or Config
    app.config.from_object(config_object)

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        sqlite_file = os.path.join(app.instance_path, "meeting_ai.sqlite")
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{sqlite_file}"

    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "") or ""
    if uri.startswith("sqlite:") and ":memory:" not in uri:
        parsed = urlparse(uri)
        db_path = unquote(parsed.path or "")

        if db_path.startswith("/") and not os.path.isabs(db_path):
            db_path = os.path.join(backend_dir, db_path.lstrip("/"))

        if db_path and os.path.isabs(db_path):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        elif db_path:
            os.makedirs(os.path.dirname(os.path.join(backend_dir, db_path.lstrip("/"))), exist_ok=True)

    db.init_app(app)

    # ── Flask-Login ───────────────────────────────────────────
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login_page"

    @login_manager.user_loader
    def load_user(user_id: str):
        from .models import User
        return User.query.get(int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        # API routes → JSON 401; UI routes → redirect to /login
        if request.path.startswith("/api/") or request.path.startswith("/auth/"):
            return {"error": "Authentication required", "code": "UNAUTHENTICATED"}, 401
        return redirect("/login")

    # ── Blueprints ────────────────────────────────────────────
    from .routes.ui           import bp as ui_bp
    from .routes.auth         import bp as auth_bp
    from .routes.projects     import bp as projects_bp
    from .routes.meetings     import bp as meetings_bp
    from .routes.action_items import bp as action_items_bp
    from .routes.misc         import bp as misc_bp

    app.register_blueprint(ui_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp,     url_prefix="/api")
    app.register_blueprint(meetings_bp,     url_prefix="/api")
    app.register_blueprint(action_items_bp, url_prefix="/api")
    app.register_blueprint(misc_bp,         url_prefix="/api")

    # ── DB / auto-migrations ──────────────────────────────────
    with app.app_context():
        db.create_all()

        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "") or ""
        if uri.startswith("sqlite:"):
            # projects.participants_json
            cols = db.session.execute(text("PRAGMA table_info(projects)")).all()
            col_names = {c[1] for c in cols}
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
            for col, typedef in [
                ("processing_stage",       "TEXT"),
                ("processing_progress",    "INTEGER"),
                ("processing_started_at",  "DATETIME"),
                ("processing_finished_at", "DATETIME"),
                ("notes",                  "TEXT"),
            ]:
                if col not in col_names:
                    db.session.execute(text(f"ALTER TABLE meetings ADD COLUMN {col} {typedef}"))

            # action_items.last_rementioned_meeting_id
            cols = db.session.execute(text("PRAGMA table_info(action_items)")).fetchall()
            col_names = {c[1] for c in cols}
            if "last_rementioned_meeting_id" not in col_names:
                db.session.execute(text("ALTER TABLE action_items ADD COLUMN last_rementioned_meeting_id INTEGER"))

            # projects: archived, name_aliases_json, user_id (auth)
            cols = db.session.execute(text("PRAGMA table_info(projects)")).fetchall()
            col_names = {c[1] for c in cols}
            if "archived" not in col_names:
                db.session.execute(text("ALTER TABLE projects ADD COLUMN archived INTEGER DEFAULT 0"))
            if "name_aliases_json" not in col_names:
                db.session.execute(text("ALTER TABLE projects ADD COLUMN name_aliases_json TEXT"))
            if "user_id" not in col_names:
                db.session.execute(text("ALTER TABLE projects ADD COLUMN user_id INTEGER REFERENCES users(id)"))

            db.session.commit()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
