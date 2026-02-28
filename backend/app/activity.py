"""Optional activity logging for audit."""
from __future__ import annotations

from ..db import db
from ..models import ActivityLog


def log_activity(
    project_id: int | None = None,
    meeting_id: int | None = None,
    action_item_id: int | None = None,
    action: str = "",
    details: str | None = None,
) -> None:
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
