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

    completed_count = ActionItem.query.filter_by(project_id=project_id, status="completed").count()
    pending_count = len(pending_items)
    meetings_count = Meeting.query.filter_by(project_id=project_id).count()
    last_meeting_at = meetings[0].created_at.isoformat() if meetings else None

    return {
        "project": project.to_dict(),
        "stats": {
            "meetings_count": meetings_count,
            "pending_action_items_count": pending_count,
            "completed_action_items_count": completed_count,
            "last_meeting_at": last_meeting_at,
        },
        "meetings": [m.to_dict(include_children=True) for m in meetings],
        "pending_action_items": [ai.to_dict() for ai in pending_items],
    }


@bp.get("/projects/<int:project_id>/participants")
def get_project_participants(project_id: int):
    project = Project.query.get_or_404(project_id)
    return {"project": project.to_dict()}


@bp.put("/projects/<int:project_id>/participants")
def set_project_participants(project_id: int):
    """
    Lightweight, viva-friendly manual speaker labeling:
    store participants list on the Project as JSON.
    """
    import json

    project = Project.query.get_or_404(project_id)
    payload = request.get_json(force=True, silent=False) or {}
    participants = payload.get("participants") or []

    if not isinstance(participants, list):
        return {"error": "participants must be a list of strings"}, 400

    cleaned: list[str] = []
    for p in participants:
        if not isinstance(p, str):
            continue
        name = p.strip()
        if name and name not in cleaned:
            cleaned.append(name)

    project.participants_json = json.dumps(cleaned)
    db.session.commit()
    return {"project": project.to_dict()}

