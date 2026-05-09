import os
from datetime import datetime

from flask import Blueprint, current_app, request, send_file
from flask_login import login_required, current_user

from ..db import db
from ..models import Meeting, Project, Transcript, Summary, ActionItem
from ..services.processor import process_meeting as process_meeting_pipeline


bp = Blueprint("meetings", __name__)

_background_jobs: dict[int, bool] = {}


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _owned_meeting_or_404(meeting_id: int) -> Meeting:
    """Return meeting if its project belongs to current_user, else 404."""
    meeting = Meeting.query.get_or_404(meeting_id)
    Project.query.filter_by(id=meeting.project_id, user_id=current_user.id).first_or_404()
    return meeting


@bp.post("/meetings/start")
@login_required
def start_meeting():
    payload    = request.get_json(force=True, silent=False) or {}
    project_id = payload.get("project_id")
    title      = (payload.get("title") or "").strip() or None

    if not project_id:
        return {"error": "project_id is required"}, 400

    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()
    if not project:
        return {"error": "invalid project_id"}, 404

    started_at = datetime.utcnow()
    meeting = Meeting(project_id=project.id, title=title, started_at=started_at, status="created")
    db.session.add(meeting)
    db.session.commit()

    return {"meeting": meeting.to_dict()}, 201


@bp.post("/meetings/<int:meeting_id>/stop")
@login_required
def stop_meeting(meeting_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    meeting = _owned_meeting_or_404(meeting_id)
    meeting.ended_at = datetime.utcnow()
    if payload.get("title"):
        meeting.title = (payload.get("title") or "").strip() or meeting.title
    db.session.commit()
    return {"meeting": meeting.to_dict()}


@bp.post("/meetings/<int:meeting_id>/upload_audio")
@login_required
def upload_audio(meeting_id: int):
    meeting = _owned_meeting_or_404(meeting_id)

    if "audio" not in request.files:
        return {"error": "missing file field 'audio' in multipart/form-data"}, 400

    file = request.files["audio"]
    if not file or not file.filename:
        return {"error": "empty file"}, 400

    upload_root = current_app.config["UPLOAD_DIR"]
    dest_dir = os.path.join(upload_root, f"project_{meeting.project_id}", f"meeting_{meeting.id}")
    _ensure_dir(dest_dir)

    _, ext = os.path.splitext(file.filename)
    ext = ext or ".webm"
    dest_path = os.path.join(dest_dir, f"original{ext}")

    file.save(dest_path)

    meeting.audio_path = dest_path
    meeting.status     = "audio_uploaded"
    db.session.commit()

    return {"meeting": meeting.to_dict()}, 200


@bp.get("/meetings/<int:meeting_id>/audio")
@login_required
def get_meeting_audio(meeting_id: int):
    meeting = _owned_meeting_or_404(meeting_id)
    if not meeting.audio_path or not os.path.isfile(meeting.audio_path):
        return {"error": "no audio for this meeting"}, 404
    ext = os.path.splitext(meeting.audio_path)[1].lower()
    mimetypes = {
        ".webm": "audio/webm",
        ".wav":  "audio/wav",
        ".mp3":  "audio/mpeg",
        ".m4a":  "audio/mp4",
        ".ogg":  "audio/ogg",
    }
    mimetype = mimetypes.get(ext, "application/octet-stream")
    return send_file(
        meeting.audio_path,
        mimetype=mimetype,
        as_attachment=False,
        download_name=os.path.basename(meeting.audio_path),
    )


@bp.post("/meetings/<int:meeting_id>/process")
@login_required
def process_meeting(meeting_id: int):
    meeting = _owned_meeting_or_404(meeting_id)

    if not meeting.audio_path:
        return {"error": "no audio uploaded for this meeting"}, 400

    try:
        payload    = request.get_json(force=True, silent=True) or {}
        async_mode = payload.get("async", True)

        if async_mode:
            if _background_jobs.get(meeting.id):
                return {"meeting": meeting.to_dict(include_children=True), "message": "already processing"}, 202

            meeting.status              = "processing"
            meeting.processing_stage    = meeting.processing_stage or "queued"
            meeting.processing_progress = meeting.processing_progress or 0
            meeting.processing_started_at = meeting.processing_started_at or datetime.utcnow()
            meeting.processing_error    = None
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
    except Exception as e:
        meeting.status = "failed"
        meeting.processing_error = str(e)
        db.session.commit()
        return {"error": "processing failed", "details": str(e)}, 500


@bp.get("/meetings/<int:meeting_id>")
@login_required
def get_meeting(meeting_id: int):
    meeting = _owned_meeting_or_404(meeting_id)
    return {"meeting": meeting.to_dict(include_children=True)}


@bp.patch("/meetings/<int:meeting_id>")
@login_required
def update_meeting(meeting_id: int):
    meeting = _owned_meeting_or_404(meeting_id)
    payload = request.get_json(force=True, silent=True) or {}
    if "notes" in payload:
        meeting.notes = (payload.get("notes") or "").strip() or None
    if "title" in payload:
        meeting.title = (payload.get("title") or "").strip() or None
    db.session.commit()
    return {"meeting": meeting.to_dict(include_children=True)}


@bp.post("/meetings/<int:meeting_id>/duplicate")
@login_required
def duplicate_meeting(meeting_id: int):
    meeting = _owned_meeting_or_404(meeting_id)
    new_meeting = Meeting(
        project_id=meeting.project_id,
        title=(meeting.title or "") + " (copy)",
        status="created",
    )
    db.session.add(new_meeting)
    db.session.flush()
    if meeting.transcript:
        t = meeting.transcript
        new_t = Transcript(
            meeting_id=new_meeting.id,
            text=t.text or "",
            language=t.language,
            model_name=t.model_name,
            speaker_segments_json=t.speaker_segments_json,
        )
        db.session.add(new_t)
    if meeting.summary:
        s = meeting.summary
        new_s = Summary(
            meeting_id=new_meeting.id,
            summary_text=s.summary_text or "",
            decisions_json=s.decisions_json,
            action_items_json=s.action_items_json,
            model_name=s.model_name,
        )
        db.session.add(new_s)
    db.session.commit()
    return {"meeting": new_meeting.to_dict(include_children=True)}, 201


@bp.delete("/meetings/<int:meeting_id>")
@login_required
def delete_meeting(meeting_id: int):
    meeting    = _owned_meeting_or_404(meeting_id)
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
@login_required
def generate_speaker_segments(meeting_id: int):
    import json
    import re

    meeting = _owned_meeting_or_404(meeting_id)
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


@bp.get("/meetings/<int:meeting_id>/export/pdf")
@login_required
def export_meeting_pdf(meeting_id: int):
    import html as _html
    import io
    import json as _json
    import re

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable, Paragraph, SimpleDocTemplate, Spacer,
    )

    meeting = _owned_meeting_or_404(meeting_id)
    project    = meeting.project
    summary    = meeting.summary
    transcript = meeting.transcript

    # ── PDF document ──────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=22 * mm, bottomMargin=22 * mm,
        title=meeting.title or "Meeting Minutes",
        author="Meeting AI",
    )

    base   = getSampleStyleSheet()
    INDIGO = colors.HexColor("#6366f1")
    DARK   = colors.HexColor("#0f172a")
    MUTED  = colors.HexColor("#64748b")

    def S(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    sty_brand  = S("brand",  textColor=INDIGO,  fontSize=9,    fontName="Helvetica-Bold", spaceAfter=6)
    sty_title  = S("title",  textColor=DARK,    fontSize=20,   fontName="Helvetica-Bold", spaceAfter=4, leading=26)
    sty_meta   = S("meta",   textColor=MUTED,   fontSize=9,    spaceAfter=2)
    sty_h2     = S("h2",     textColor=INDIGO,  fontSize=12,   fontName="Helvetica-Bold", spaceAfter=4, spaceBefore=12, leading=16)
    sty_body   = S("body",   textColor=DARK,    fontSize=10,   spaceAfter=4,  leading=15)
    sty_bullet = S("bullet", textColor=DARK,    fontSize=10,   spaceAfter=3,  leading=14, leftIndent=10)
    sty_seg    = S("seg",    textColor=DARK,    fontSize=9.5,  spaceAfter=5,  leading=14)

    def esc(s):
        return _html.escape(str(s or ""))

    story = []

    # Header
    story.append(Paragraph("Meeting AI", sty_brand))
    story.append(Paragraph(esc(meeting.title or "Untitled Meeting"), sty_title))
    date_str = meeting.created_at.strftime("%d %B %Y, %H:%M") if meeting.created_at else "—"
    story.append(Paragraph(f"Project: {esc(project.name)}", sty_meta))
    story.append(Paragraph(f"Date: {date_str}", sty_meta))
    story.append(Paragraph(f"Status: {esc(meeting.status.replace('_', ' ').title())}", sty_meta))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=INDIGO, spaceAfter=6))

    # Summary
    story.append(Paragraph("Summary", sty_h2))
    summary_text = summary.summary_text if summary else None
    story.append(Paragraph(
        esc(summary_text) if summary_text else
        "No summary available — process the meeting to generate one.",
        sty_body,
    ))

    # Decisions
    if summary:
        decisions = []
        try:
            decisions = _json.loads(summary.decisions_json) if summary.decisions_json else []
        except Exception:
            pass
        if decisions:
            story.append(Paragraph("Decisions", sty_h2))
            for d in decisions:
                text = d.get("text") if isinstance(d, dict) else str(d)
                story.append(Paragraph(f"• {esc(text)}", sty_bullet))

    # Action Items
    if summary:
        items = []
        try:
            items = _json.loads(summary.action_items_json) if summary.action_items_json else []
        except Exception:
            pass
        if items:
            story.append(Paragraph("Action Items", sty_h2))
            for ai in items:
                if isinstance(ai, dict):
                    who     = ai.get("who") or ""
                    will_do = ai.get("will_do") or "do"
                    what    = ai.get("what") or ""
                    by_when = ai.get("by_when") or ""
                    parts   = f"{who + ' — ' if who else ''}{will_do} — {what}"
                    if by_when:
                        parts += f" (by {by_when})"
                    line = f"• {esc(parts)}"
                else:
                    line = f"• {esc(str(ai))}"
                story.append(Paragraph(line, sty_bullet))

    # Transcript
    if transcript:
        story.append(Paragraph("Transcript", sty_h2))
        segments = []
        try:
            segments = _json.loads(transcript.speaker_segments_json) if transcript.speaker_segments_json else []
        except Exception:
            pass

        if segments:
            for seg in segments:
                spk  = esc(seg.get("speaker") or "Unknown")
                text = esc(seg.get("text") or "")
                if text:
                    story.append(Paragraph(f"<b>{spk}:</b> {text}", sty_seg))
        elif transcript.text:
            story.append(Paragraph(esc(transcript.text), sty_body))

    doc.build(story)
    buf.seek(0)

    safe = re.sub(r"[^\w\-]", "_", meeting.title or "meeting").strip("_") or "meeting"
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{safe}_minutes.pdf",
    )


@bp.patch("/meetings/<int:meeting_id>/speaker_segments")
@login_required
def update_speaker_segments(meeting_id: int):
    import json

    meeting = _owned_meeting_or_404(meeting_id)
    if not meeting.transcript:
        return {"error": "meeting has no transcript yet (process meeting first)"}, 400

    payload  = request.get_json(force=True, silent=False) or {}
    segments = payload.get("speaker_segments")
    if not isinstance(segments, list):
        return {"error": "speaker_segments must be a list"}, 400

    cleaned = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        idx     = seg.get("idx")
        text    = (seg.get("text") or "").strip()
        speaker = (seg.get("speaker") or "").strip() or None
        if isinstance(idx, int) and text:
            cleaned.append({"idx": idx, "speaker": speaker, "text": text})

    meeting.transcript.speaker_segments_json = json.dumps(cleaned)
    db.session.commit()
    return {"transcript": meeting.transcript.to_dict()}
