import os
from datetime import datetime

from flask import Blueprint, current_app, request

from ..db import db
from ..models import Meeting, Project, Transcript, Summary, ActionItem
from ..services.processor import process_meeting as process_meeting_pipeline


bp = Blueprint("meetings", __name__)


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


@bp.post("/meetings/start")
def start_meeting():
    """
    Creates a Meeting row immediately so the frontend can upload audio against it.
    """
    payload = request.get_json(force=True, silent=False) or {}
    project_id = payload.get("project_id")
    title = (payload.get("title") or "").strip() or None

    if not project_id:
        return {"error": "project_id is required"}, 400

    project = Project.query.get(project_id)
    if not project:
        return {"error": "invalid project_id"}, 404

    started_at = datetime.utcnow()
    meeting = Meeting(project_id=project.id, title=title, started_at=started_at, status="created")
    db.session.add(meeting)
    db.session.commit()

    return {"meeting": meeting.to_dict()}, 201


@bp.post("/meetings/<int:meeting_id>/stop")
def stop_meeting(meeting_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    meeting = Meeting.query.get_or_404(meeting_id)
    meeting.ended_at = datetime.utcnow()
    if payload.get("title"):
        meeting.title = (payload.get("title") or "").strip() or meeting.title
    db.session.commit()
    return {"meeting": meeting.to_dict()}


@bp.post("/meetings/<int:meeting_id>/upload_audio")
def upload_audio(meeting_id: int):
    """
    Prototype upload:
    - multipart/form-data with file field: "audio"
    Saves under: data/uploads/project_<id>/meeting_<id>/original.<ext>
    """
    meeting = Meeting.query.get_or_404(meeting_id)

    if "audio" not in request.files:
        return {"error": "missing file field 'audio' in multipart/form-data"}, 400

    file = request.files["audio"]
    if not file or not file.filename:
        return {"error": "empty file"}, 400

    upload_root = current_app.config["UPLOAD_DIR"]
    dest_dir = os.path.join(upload_root, f"project_{meeting.project_id}", f"meeting_{meeting.id}")
    _ensure_dir(dest_dir)

    _, ext = os.path.splitext(file.filename)
    ext = ext or ".webm"  # common browser recording default
    dest_path = os.path.join(dest_dir, f"original{ext}")

    file.save(dest_path)

    meeting.audio_path = dest_path
    meeting.status = "audio_uploaded"
    db.session.commit()

    return {"meeting": meeting.to_dict()}, 200


@bp.post("/meetings/<int:meeting_id>/process")
def process_meeting(meeting_id: int):
    """
    Post-meeting processing (Phase 2):
    - ASR (Whisper if installed; otherwise fallback stub)
    - retrieve project context (prior summaries + pending action items)
    - summarization (Transformers if installed; otherwise fallback)
    - rule-based action item extraction (simple, explainable)
    """
    meeting = Meeting.query.get_or_404(meeting_id)

    if not meeting.audio_path:
        return {"error": "no audio uploaded for this meeting"}, 400

    try:
        meeting = process_meeting_pipeline(meeting)
        return {"meeting": meeting.to_dict(include_children=True)}, 200
    except Exception as e:  # keep prototype simple; later we’ll add structured error handling/logging
        meeting.status = "failed"
        meeting.processing_error = str(e)
        db.session.commit()
        return {"error": "processing failed", "details": str(e)}, 500


@bp.get("/meetings/<int:meeting_id>")
def get_meeting(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    return {"meeting": meeting.to_dict(include_children=True)}

