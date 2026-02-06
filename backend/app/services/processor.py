from __future__ import annotations

import json

from ..db import db
from ..models import ActionItem, Meeting, Summary, Transcript
from .action_extractor import extract_decisions_and_actions
from .asr_whisper import transcribe_with_whisper
from .summarizer import fallback_summary, summarize_with_transformers


def _auto_resolve_action_items_from_transcript(meeting: Meeting, transcript_text: str) -> int:
    """
    Simple, explainable heuristic:
    If someone says phrases like "action item 12 completed/done/closed", mark it completed.

    This gives you an "agentic" feeling in demo without needing an LLM.
    """
    import re

    pattern = re.compile(
        r"\baction\s*item\s*(?P<id>\d+)\s*(?:is\s*)?(?:done|completed|closed|resolved)\b",
        re.IGNORECASE,
    )
    ids = {int(m.group("id")) for m in pattern.finditer(transcript_text or "")}
    if not ids:
        return 0

    items = (
        ActionItem.query.filter(ActionItem.project_id == meeting.project_id)
        .filter(ActionItem.id.in_(list(ids)))
        .all()
    )
    count = 0
    for ai in items:
        if ai.status != "completed":
            ai.status = "completed"
            ai.resolved_in_meeting_id = meeting.id
            count += 1
    return count


def build_context_for_project(project_id: int, max_meetings: int = 5) -> str:
    """
    Context memory to feed into summarization:
    - last N summaries
    - currently pending action items

    Keeping this as a plain string is simple + explainable for the prototype.
    """
    recent_summaries = (
        Summary.query.join(Meeting, Summary.meeting_id == Meeting.id)
        .filter(Meeting.project_id == project_id)
        .order_by(Summary.created_at.desc())
        .limit(max_meetings)
        .all()
    )

    pending_items = (
        ActionItem.query.filter_by(project_id=project_id, status="pending")
        .order_by(ActionItem.created_at.asc())
        .all()
    )

    parts: list[str] = []
    if recent_summaries:
        parts.append("PROJECT CONTEXT (previous meeting summaries):")
        for i, s in enumerate(reversed(recent_summaries), start=1):
            parts.append(f"- Summary {i}: {s.summary_text}")

    if pending_items:
        parts.append("\nPENDING ACTION ITEMS (carry-forward):")
        for ai in pending_items:
            due = ai.by_when.isoformat() if ai.by_when else "N/A"
            who = ai.who or "Unassigned"
            parts.append(f"- [{ai.id}] {who} – {ai.what} – due: {due}")

    return "\n".join(parts).strip()


def process_meeting(meeting: Meeting) -> Meeting:
    """
    Orchestrates post-meeting processing:
    - ASR (Whisper if installed, else stub/fallback)
    - context retrieval
    - summarization (Transformers if installed, else fallback)
    - rule-based decisions + action items extraction
    - persist Transcript/Summary/ActionItem
    """
    if not meeting.audio_path:
        raise ValueError("meeting has no audio_path")

    # --- ASR ---
    try:
        asr = transcribe_with_whisper(meeting.audio_path, model_size="small")
        transcript_text = asr.text
        transcript_model = asr.model_name
        transcript_lang = asr.language
    except Exception:
        # Keep runnable even without heavy ML deps.
        transcript_text = (
            "ASR disabled (install backend/requirements-ml.txt to enable Whisper).\n"
            "This placeholder transcript keeps the pipeline demo-able."
        )
        transcript_model = "stub"
        transcript_lang = None

    transcript = Transcript.query.filter_by(meeting_id=meeting.id).first()
    if transcript:
        transcript.text = transcript_text
        transcript.language = transcript_lang
        transcript.model_name = transcript_model
    else:
        transcript = Transcript(
            meeting_id=meeting.id,
            text=transcript_text,
            language=transcript_lang,
            model_name=transcript_model,
        )
        db.session.add(transcript)

    # --- Context memory (project-based) ---
    context_text = build_context_for_project(meeting.project_id)

    # --- Summarization ---
    summarization_input = "\n\n".join(
        [
            context_text if context_text else "PROJECT CONTEXT: (none)",
            "CURRENT MEETING TRANSCRIPT:",
            transcript_text,
        ]
    )

    try:
        summ = summarize_with_transformers(summarization_input)
    except Exception:
        summ = fallback_summary(summarization_input)

    # --- Extraction ---
    extraction = extract_decisions_and_actions(transcript_text)

    # --- Auto-resolve previous action items if transcript explicitly closes them ---
    _auto_resolve_action_items_from_transcript(meeting, transcript_text)

    # Persist action items extracted in this meeting (project-scoped)
    extracted_items_payload: list[dict] = []
    for item in extraction.action_items:
        ai = ActionItem(
            project_id=meeting.project_id,
            created_in_meeting_id=meeting.id,
            who=item.who,
            will_do=item.will_do,
            what=item.what,
            by_when=item.by_when,
            status="pending",
        )
        db.session.add(ai)
        extracted_items_payload.append(
            {"who": item.who, "will_do": item.will_do, "what": item.what, "by_when": item.by_when.isoformat() if item.by_when else None}
        )

    # --- Summary persistence ---
    summary = Summary.query.filter_by(meeting_id=meeting.id).first()
    decisions_json = json.dumps(extraction.decisions)
    action_items_json = json.dumps(extracted_items_payload)

    if summary:
        summary.summary_text = summ.summary_text
        summary.decisions_json = decisions_json
        summary.action_items_json = action_items_json
        summary.model_name = summ.model_name
    else:
        summary = Summary(
            meeting_id=meeting.id,
            summary_text=summ.summary_text,
            decisions_json=decisions_json,
            action_items_json=action_items_json,
            model_name=summ.model_name,
        )
        db.session.add(summary)

    meeting.status = "processed"
    meeting.processing_error = None
    db.session.commit()
    return meeting

