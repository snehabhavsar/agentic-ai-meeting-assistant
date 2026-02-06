from flask import Blueprint, render_template


bp = Blueprint("ui", __name__)


@bp.get("/")
def index():
    # Single-page prototype UI (Phase 2). React can be added later if needed.
    return render_template("index.html")

