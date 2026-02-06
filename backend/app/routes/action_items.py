from datetime import date

from flask import Blueprint, request

from ..db import db
from ..models import ActionItem, Project, Meeting


bp = Blueprint("action_items", __name__)


@bp.get("/projects/<int:project_id>/action_items")
def list_action_items(project_id: int):
    project = Project.query.get_or_404(project_id)
    status = (request.args.get("status") or "").strip().lower()

    q = ActionItem.query.filter_by(project_id=project.id)
    if status:
        q = q.filter_by(status=status)

    items = q.order_by(ActionItem.created_at.desc()).limit(200).all()
    return {"action_items": [ai.to_dict() for ai in items]}


@bp.post("/projects/<int:project_id>/action_items")
def create_action_item(project_id: int):
    """
    Manual creation (useful for demo / correction).
    """
    project = Project.query.get_or_404(project_id)
    payload = request.get_json(force=True, silent=False) or {}

    what = (payload.get("what") or "").strip()
    if not what:
        return {"error": "what is required"}, 400

    created_in_meeting_id = payload.get("created_in_meeting_id")
    if created_in_meeting_id:
        Meeting.query.get_or_404(created_in_meeting_id)

    by_when = None
    if payload.get("by_when"):
        # Expect ISO date: YYYY-MM-DD
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

    return {"action_item": ai.to_dict()}, 201


@bp.patch("/action_items/<int:action_item_id>")
def update_action_item(action_item_id: int):
    """
    Minimal update endpoint:
    - mark completed/pending
    - edit fields (for demo corrections)
    """
    ai = ActionItem.query.get_or_404(action_item_id)
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
    return {"action_item": ai.to_dict()}

