from flask import Blueprint, request
from sqlalchemy import or_

from ..db import db
from ..models import Project, Meeting, ActionItem
from ..services.processor import _apply_name_alias_to_who, _get_name_aliases


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

    try:
        from ..activity import log_activity
        log_activity(project_id=project.id, action="project_created", details=name)
    except Exception:
        pass

    return {"project": project.to_dict()}, 201


@bp.get("/projects")
def list_projects():
    show_archived = request.args.get("archived", "0").strip() == "1"
    q = Project.query.order_by(Project.created_at.desc())
    if not show_archived:
        q = q.filter(or_(Project.archived == False, Project.archived == None))
    projects = q.all()
    return {"projects": [p.to_dict() for p in projects]}


@bp.delete("/projects/<int:project_id>")
def delete_project(project_id: int):
    """Delete a project and all its meetings, action items, etc. (cascade)."""
    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    return {"success": True, "message": "deleted"}


@bp.patch("/projects/<int:project_id>")
def update_project(project_id: int):
    import json as _json

    project = Project.query.get_or_404(project_id)
    payload = request.get_json(force=True, silent=True) or {}
    if "archived" in payload:
        project.archived = bool(payload["archived"])
    if "description" in payload:
        project.description = (payload.get("description") or "").strip() or None
    if "name_aliases" in payload:
        aliases = payload.get("name_aliases")
        if aliases is None:
            project.name_aliases_json = None
        elif isinstance(aliases, dict):
            cleaned = {str(k).strip(): str(v).strip() for k, v in aliases.items() if k and v}
            project.name_aliases_json = _json.dumps(cleaned) if cleaned else None
        else:
            return {"error": "name_aliases must be an object, e.g. {\"kagi\": \"Gargi\"}"}, 400
    db.session.commit()
    return {"project": project.to_dict()}


@bp.get("/projects/<int:project_id>/history")
def project_history(project_id: int):
    project = Project.query.get_or_404(project_id)

    q_meetings = Meeting.query.filter_by(project_id=project_id).order_by(Meeting.created_at.desc())
    from_param = request.args.get("from", "").strip()
    to_param = request.args.get("to", "").strip()
    status_param = request.args.get("status", "").strip()
    search_q = request.args.get("q", "").strip()

    if from_param:
        try:
            from datetime import datetime
            q_meetings = q_meetings.filter(Meeting.created_at >= datetime.fromisoformat(from_param.replace("Z", "+00:00")))
        except Exception:
            pass
    if to_param:
        try:
            from datetime import datetime
            q_meetings = q_meetings.filter(Meeting.created_at <= datetime.fromisoformat(to_param.replace("Z", "+00:00")))
        except Exception:
            pass
    if status_param:
        q_meetings = q_meetings.filter(Meeting.status == status_param)

    meetings = q_meetings.limit(50).all()

    if search_q:
        search_lower = search_q.lower()
        filtered = []
        for m in meetings:
            if search_lower in (m.title or "").lower():
                filtered.append(m)
                continue
            if m.transcript and search_lower in (m.transcript.text or "").lower():
                filtered.append(m)
        meetings = filtered

    pending_items = (
        ActionItem.query.filter_by(project_id=project_id, status="pending")
        .order_by(ActionItem.created_at.asc())
        .all()
    )

    completed_count = ActionItem.query.filter_by(project_id=project_id, status="completed").count()
    pending_count = len(pending_items)
    meetings_count = Meeting.query.filter_by(project_id=project_id).count()
    last_meeting_at = meetings[0].created_at.isoformat() if meetings else None

    aliases = _get_name_aliases(project_id)
    pending_with_aliases = [
        {**ai.to_dict(), "who": _apply_name_alias_to_who(ai.who, aliases)}
        for ai in pending_items
    ]
    return {
        "project": project.to_dict(),
        "stats": {
            "meetings_count": meetings_count,
            "pending_action_items_count": pending_count,
            "completed_action_items_count": completed_count,
            "last_meeting_at": last_meeting_at,
        },
        "meetings": [m.to_dict(include_children=True) for m in meetings],
        "pending_action_items": pending_with_aliases,
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

