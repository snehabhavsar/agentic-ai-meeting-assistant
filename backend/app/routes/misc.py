import os
import shutil
from datetime import datetime

from flask import Blueprint, current_app, request, send_file
from flask_login import login_required, current_user

from ..db import db
from ..models import ActivityLog, Project, Meeting, ActionItem


bp = Blueprint("misc", __name__)


@bp.get("/backup")
@login_required
def backup_db():
    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    if not uri.startswith("sqlite:///") or ":memory:" in uri:
        return {"error": "Backup only supported for SQLite file database"}, 400
    path = uri.replace("sqlite:///", "").lstrip("/")
    if not os.path.isabs(path):
        path = os.path.join(current_app.instance_path, path)
    if not os.path.exists(path):
        return {"error": "Database file not found"}, 404
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest = path + f".backup_{timestamp}"
    try:
        shutil.copy2(path, dest)
        return send_file(
            dest,
            as_attachment=True,
            download_name=f"meeting_ai_backup_{timestamp}.sqlite",
            mimetype="application/x-sqlite3",
        )
    except Exception as e:
        return {"error": str(e)}, 500
    finally:
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except Exception:
                pass


@bp.get("/projects/<int:project_id>/activity")
@login_required
def project_activity(project_id: int):
    Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
    limit = min(int(request.args.get("limit", 50)), 200)
    entries = (
        ActivityLog.query.filter_by(project_id=project_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {"activity": [e.to_dict() for e in entries]}


def log_activity(project_id=None, meeting_id=None, action_item_id=None, action="", details=None):
    try:
        entry = ActivityLog(
            project_id=project_id,
            meeting_id=meeting_id,
            action_item_id=action_item_id,
            action=action,
            details=details,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()
