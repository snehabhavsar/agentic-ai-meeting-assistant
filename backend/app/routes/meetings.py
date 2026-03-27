import os
from datetime import datetime

from flask import Blueprint, current_app, request, send_file

from ..db import db
from ..models import Meeting, Project, Transcript, Summary, ActionItem
from ..services.processor import process_meeting as process_meeting_pipeline


bp = Blueprint("meetings", __name__)

_background_jobs: dict[int, bool] = {}


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


@bp.get("/meetings/<int:meeting_id>/audio")
def get_meeting_audio(meeting_id: int):
    """
    Stream the meeting recording so you can play it in the browser.
    Returns 404 if no audio was uploaded for this meeting.
    """
    meeting = Meeting.query.get_or_404(meeting_id)
    if not meeting.audio_path or not os.path.isfile(meeting.audio_path):
        return {"error": "no audio for this meeting"}, 404
    ext = os.path.splitext(meeting.audio_path)[1].lower()
    mimetypes = {
        ".webm": "audio/webm",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
    }
    mimetype = mimetypes.get(ext, "application/octet-stream")
    return send_file(
        meeting.audio_path,
        mimetype=mimetype,
        as_attachment=False,
        download_name=os.path.basename(meeting.audio_path),
    )


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
        payload = request.get_json(force=True, silent=True) or {}
        async_mode = payload.get("async", True)

        if async_mode:
            if _background_jobs.get(meeting.id):
                return {"meeting": meeting.to_dict(include_children=True), "message": "already processing"}, 202

            meeting.status = "processing"
            meeting.processing_stage = meeting.processing_stage or "queued"
            meeting.processing_progress = meeting.processing_progress or 0
            meeting.processing_started_at = meeting.processing_started_at or datetime.utcnow()
            meeting.processing_error = None
            db.session.commit()

            _background_jobs[meeting.id] = True

            import threading

            app = current_app._get_current_object()

            def _run_job(mid: int):
                with app.app_context():
                    try:
                        m = Meeting.query.get(mid)
                        if m:
                            process_meeting_pipeline(m)
                    except Exception as e:
                        m = Meeting.query.get(mid)
                        if m:
                            m.status = "failed"
                            m.processing_error = str(e)
                            db.session.commit()
                    finally:
                        _background_jobs.pop(mid, None)

            threading.Thread(target=_run_job, args=(meeting.id,), daemon=True).start()
            return {"meeting": meeting.to_dict(include_children=True), "async": True}, 202

        meeting = process_meeting_pipeline(meeting)
        return {"meeting": meeting.to_dict(include_children=True), "async": False}, 200
    except Exception as e:  # keep prototype simple; later we’ll add structured error handling/logging
        meeting.status = "failed"
        meeting.processing_error = str(e)
        db.session.commit()
        return {"error": "processing failed", "details": str(e)}, 500


@bp.get("/meetings/<int:meeting_id>")
def get_meeting(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    return {"meeting": meeting.to_dict(include_children=True)}

@bp.patch("/meetings/<int:meeting_id>")
def update_meeting(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    payload = request.get_json(force=True, silent=True) or {}
    if "notes" in payload:
        meeting.notes = (payload.get("notes") or "").strip() or None
    if "title" in payload:
        meeting.title = (payload.get("title") or "").strip() or None
    db.session.commit()
    return {"meeting": meeting.to_dict(include_children=True)}


@bp.post("/meetings/<int:meeting_id>/duplicate")
def duplicate_meeting(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    new_meeting = Meeting(
        project_id=meeting.project_id,
        title=(meeting.title or "") + " (copy)",
        status="created",
    )
    db.session.add(new_meeting)
    db.session.flush()
    if meeting.transcript:
        t = meeting.transcript
        new_t = Transcript(meeting_id=new_meeting.id, text=t.text or "", language=t.language, model_name=t.model_name, speaker_segments_json=t.speaker_segments_json)
        db.session.add(new_t)
    if meeting.summary:
        s = meeting.summary
        new_s = Summary(meeting_id=new_meeting.id, summary_text=s.summary_text or "", decisions_json=s.decisions_json, action_items_json=s.action_items_json, model_name=s.model_name)
        db.session.add(new_s)
    db.session.commit()
    return {"meeting": new_meeting.to_dict(include_children=True)}, 201




@bp.delete("/meetings/<int:meeting_id>")
def delete_meeting(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    project_id = meeting.project_id
    for ai in ActionItem.query.filter(
        (ActionItem.created_in_meeting_id == meeting_id)
        | (ActionItem.resolved_in_meeting_id == meeting_id)
        | (ActionItem.last_rementioned_meeting_id == meeting_id)
    ):
        if ai.created_in_meeting_id == meeting_id:
            ai.created_in_meeting_id = None
        if ai.resolved_in_meeting_id == meeting_id:
            ai.resolved_in_meeting_id = None
        if ai.last_rementioned_meeting_id == meeting_id:
            ai.last_rementioned_meeting_id = None
    db.session.commit()
    db.session.delete(meeting)
    db.session.commit()
    return {"success": True, "message": "deleted", "project_id": project_id}


@bp.post("/meetings/<int:meeting_id>/speaker_segments/generate")
def generate_speaker_segments(meeting_id: int):
    """
    Create transcript segments for manual speaker labeling if missing.
    """
    import json
    import re

    meeting = Meeting.query.get_or_404(meeting_id)
    if not meeting.transcript:
        return {"error": "meeting has no transcript yet (process meeting first)"}, 400

    t = meeting.transcript
    if t.speaker_segments_json:
        return {"transcript": t.to_dict()}

    text = (t.text or "").strip()
    if not text:
        t.speaker_segments_json = json.dumps([])
        db.session.commit()
        return {"transcript": t.to_dict()}

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 4:
        parts = lines
    else:
        parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

    segments = [{"idx": i + 1, "speaker": None, "text": parts[i]} for i in range(len(parts))]
    t.speaker_segments_json = json.dumps(segments)
    db.session.commit()
    return {"transcript": t.to_dict()}


@bp.patch("/meetings/<int:meeting_id>/speaker_segments")
def update_speaker_segments(meeting_id: int):
    """
    Save manual speaker labels for transcript segments.
    Body:
      { "speaker_segments": [ {idx, speaker, text}, ... ] }
    """
    import json

    meeting = Meeting.query.get_or_404(meeting_id)
    if not meeting.transcript:
        return {"error": "meeting has no transcript yet (process meeting first)"}, 400

    payload = request.get_json(force=True, silent=False) or {}
    segments = payload.get("speaker_segments")
    if not isinstance(segments, list):
        return {"error": "speaker_segments must be a list"}, 400

    cleaned = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        idx = seg.get("idx")
        text = (seg.get("text") or "").strip()
        speaker = seg.get("speaker")
        speaker = (speaker or "").strip() or None
        if isinstance(idx, int) and text:
            cleaned.append({"idx": idx, "speaker": speaker, "text": text})

    meeting.transcript.speaker_segments_json = json.dumps(cleaned)
    db.session.commit()
    return {"transcript": meeting.transcript.to_dict()}

