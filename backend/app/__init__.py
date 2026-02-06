import os

from flask import Flask
from flask_cors import CORS

from .config import Config
from .db import db


def create_app(config_object: type[Config] | None = None) -> Flask:
    """
    Flask app factory.

    Why app factory?
    - Easier testing
    - Cleaner separation of concerns
    - Allows different configs (dev/test/prod)
    """
    app = Flask(__name__, instance_relative_config=True)
    CORS(app)  # simple cross-origin support for local React dev server

    # Ensure instance folder exists (SQLite file lives here by default).
    os.makedirs(app.instance_path, exist_ok=True)

    config_object = config_object or Config
    app.config.from_object(config_object)

    db.init_app(app)

    # Register blueprints (API routes)
    from .routes.ui import bp as ui_bp
    from .routes.projects import bp as projects_bp
    from .routes.meetings import bp as meetings_bp
    from .routes.action_items import bp as action_items_bp

    app.register_blueprint(ui_bp)
    app.register_blueprint(projects_bp, url_prefix="/api")
    app.register_blueprint(meetings_bp, url_prefix="/api")
    app.register_blueprint(action_items_bp, url_prefix="/api")

    # Create tables automatically for prototype usage.
    # In later phases, we can add Flask-Migrate for migrations.
    with app.app_context():
        db.create_all()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app

