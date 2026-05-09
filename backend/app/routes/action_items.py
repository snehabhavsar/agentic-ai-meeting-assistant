from datetime import date

from flask import Blueprint, request
from flask_login import login_required, current_user

from ..db import db
from ..models import ActionItem, Project, Meeting
from ..services.processor import _apply_name_alias_to_who, _get_name_aliases


def _action_item_to_dict(ai: ActionItem, aliases: dict) -> dict:
    d = ai.to_dict()
    d["who"] = _apply_name_alias_to_who(ai.who, aliases)
    return d


def _owned_project_or_404(project_id: int) -> Project:
    return Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()


bp = Blueprint("action_items", __name__)


@bp.get("/projects/<int:project_id>/action_items")
@login_required
def list_action_items(project_id: int):
    project = _owned_project_or_404(project_id)
    status  = (request.args.get("status") or "").strip().lower()

    q = ActionItem.query.filter_by(project_id=project.id)
    if status:
        q = q.filter_by(status=status)

    items   = q.order_by(ActionItem.created_at.desc()).limit(200).all()
    aliases = _get_name_aliases(project_id)
    return {"action_items": [_action_item_to_dict(ai, aliases) for ai in items]}


@bp.post("/projects/<int:project_id>/action_items")
@login_required
def create_action_item(project_id: int):
    project = _owned_project_or_404(project_id)
    payload = request.get_json(force=True, silent=False) or {}

    what = (payload.get("what") or "").strip()
    if not what:
        return {"error": "what is required"}, 400

    created_in_meeting_id = payload.get("created_in_meeting_id")
    if created_in_meeting_id:
        Meeting.query.get_or_404(created_in_meeting_id)

    by_when = None
    if payload.get("by_when"):
        by_when = date.fromisoformat(payload["by_when"])

    ai = ActionItem(
        project_id=project.id,
        created_in_meeting_id=created_in_meeting_id,
        who=(payload.get("who") or "").strip() or None,
        will_do=(payload.get("will_do") or "").strip() or None,
        what=what,
        by_when=by_when,
        status="pending",
    )
    db.session.add(ai)
    db.session.commit()

    aliases = _get_name_aliases(project.id)
    return {"action_item": _action_item_to_dict(ai, aliases)}, 201


@bp.patch("/action_items/<int:action_item_id>")
@login_required
def update_action_item(action_item_id: int):
    ai = ActionItem.query.get_or_404(action_item_id)
    # Verify ownership via the action item's project
    Project.query.filter_by(id=ai.project_id, user_id=current_user.id).first_or_404()

    payload = request.get_json(force=True, silent=False) or {}

    if "status" in payload:
        status = (payload.get("status") or "").strip().lower()
        if status not in {"pending", "completed"}:
            return {"error": "status must be 'pending' or 'completed'"}, 400
        ai.status = status

    for field in ("who", "will_do", "what"):
        if field in payload:
            val = (payload.get(field) or "").strip()
            setattr(ai, field, val or None if field != "what" else val)

    if "by_when" in payload:
        ai.by_when = date.fromisoformat(payload["by_when"]) if payload["by_when"] else None

    if "resolved_in_meeting_id" in payload:
        if payload["resolved_in_meeting_id"] is None:
            ai.resolved_in_meeting_id = None
        else:
            Meeting.query.get_or_404(payload["resolved_in_meeting_id"])
            ai.resolved_in_meeting_id = payload["resolved_in_meeting_id"]

    db.session.commit()
    if ai.status == "completed":
        try:
            from ..activity import log_activity
            log_activity(project_id=ai.project_id, action_item_id=ai.id, action="action_completed")
        except Exception:
            pass
    aliases = _get_name_aliases(ai.project_id)
    return {"action_item": _action_item_to_dict(ai, aliases)}


@bp.delete("/action_items/<int:action_item_id>")
@login_required
def delete_action_item(action_item_id: int):
    ai = ActionItem.query.get_or_404(action_item_id)
    Project.query.filter_by(id=ai.project_id, user_id=current_user.id).first_or_404()
    project_id = ai.project_id
    db.session.delete(ai)
    db.session.commit()
    return {"success": True, "message": "deleted", "project_id": project_id}


@bp.post("/action_items/bulk_complete")
@login_required
def bulk_complete_action_items():
    payload               = request.get_json(force=True, silent=True) or {}
    ids                   = payload.get("action_item_ids") or []
    resolved_in_meeting_id = payload.get("resolved_in_meeting_id")
    if not isinstance(ids, list):
        return {"error": "action_item_ids must be a list"}, 400
    if resolved_in_meeting_id is not None:
        Meeting.query.get_or_404(resolved_in_meeting_id)

    items = ActionItem.query.filter(ActionItem.id.in_(ids), ActionItem.status == "pending").all()
    # Only update items owned by current_user (via project ownership)
    owned_project_ids = {
        p.id for p in Project.query.filter_by(user_id=current_user.id).with_entities(Project.id).all()
    }
    items = [ai for ai in items if ai.project_id in owned_project_ids]

    for ai in items:
        ai.status = "completed"
        ai.resolved_in_meeting_id = resolved_in_meeting_id
    db.session.commit()
    try:
        from ..activity import log_activity
        for ai in items:
            log_activity(project_id=ai.project_id, action_item_id=ai.id, action="action_completed")
    except Exception:
        pass
    project_id = items[0].project_id if items else None
    aliases    = _get_name_aliases(project_id) if project_id else {}
    return {"updated": len(items), "action_items": [_action_item_to_dict(ai, aliases) for ai in items]}
