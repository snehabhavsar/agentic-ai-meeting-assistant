from flask import Blueprint, request

from ..db import db
from ..models import Project, Meeting, ActionItem


bp = Blueprint("projects", __name__)


@bp.post("/projects")
def create_project():
    payload = request.get_json(force=True, silent=False) or {}
    name = (payload.get("name") or "").strip()
    description = (payload.get("description") or "").strip() or None

    if not name:
        return {"error": "name is required"}, 400

    existing = Project.query.filter_by(name=name).first()
    if existing:
        return {"error": "project with this name already exists", "project": existing.to_dict()}, 409

    project = Project(name=name, description=description)
    db.session.add(project)
    db.session.commit()

    return {"project": project.to_dict()}, 201


@bp.get("/projects")
def list_projects():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return {"projects": [p.to_dict() for p in projects]}


@bp.get("/projects/<int:project_id>/history")
def project_history(project_id: int):
    """
    Returns:
    - recent meetings (with transcript+summary if present)
    - currently pending action items (project memory)
    """
    project = Project.query.get_or_404(project_id)

    meetings = (
        Meeting.query.filter_by(project_id=project_id)
        .order_by(Meeting.created_at.desc())
        .limit(50)
        .all()
    )

    pending_items = (
        ActionItem.query.filter_by(project_id=project_id, status="pending")
        .order_by(ActionItem.created_at.asc())
        .all()
    )

    return {
        "project": project.to_dict(),
        "meetings": [m.to_dict(include_children=True) for m in meetings],
        "pending_action_items": [ai.to_dict() for ai in pending_items],
    }

