from __future__ import annotations

import json
import os

from ..db import db
from ..models import ActionItem, Meeting, Summary, Transcript
from ..config import Config
from .action_extractor import extract_decisions_and_actions
from .asr_deepgram import transcribe_with_deepgram
from .asr_whispercpp import transcribe_with_whispercpp
from .summarizer import (
    fallback_summary,
    summarize_with_gemini,
    summarize_with_transformers,
)
import traceback


def _norm(s: str | None) -> str:
    import re

    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _split_into_segments(transcript_text: str) -> list[dict]:
    """
    Lightweight segmentation for manual speaker labeling.
    We avoid heavy diarization; instead we split text and let the user assign speakers.
    """
    import re

    text = (transcript_text or "").strip()
    if not text:
        return []

    # Prefer line breaks if present (whisper.cpp often outputs them).
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 4:
        parts = lines
    else:
        # Fallback: naive sentence split.
        parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

    segments: list[dict] = []
    for i, seg_text in enumerate(parts, start=1):
        segments.append({"idx": i, "speaker": None, "text": seg_text})
    return segments


def _mark_reported_completed(meeting: Meeting, reported_list: list[dict]) -> int:
    """Mark pending items as completed when Gemini says they were reported done in the transcript."""
    if not reported_list:
        return 0
    pending = (
        ActionItem.query.filter_by(project_id=meeting.project_id, status="pending")
        .order_by(ActionItem.created_at.asc())
        .all()
    )
    count = 0
    for r in reported_list:
        who = (r.get("who") or "").strip() or None
        what = (r.get("what") or "").strip()
        if not what:
            continue
        r_who_norm = _norm(who)
        r_what_norm = _norm(what)
        for ai in pending:
            if ai.status != "pending":
                continue
            ai_who_norm = _norm(ai.who)
            ai_what_norm = _norm(ai.what)
            who_ok = r_who_norm == ai_who_norm or (not r_who_norm and not ai_who_norm)
            what_ok = (
                ai_what_norm == r_what_norm
                or (r_what_norm in ai_what_norm)
                or (ai_what_norm in r_what_norm)
            )
            if who_ok and what_ok:
                ai.status = "completed"
                ai.resolved_in_meeting_id = meeting.id
                count += 1
                pending = [x for x in pending if x.id != ai.id]
                break
    return count


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
        parts.append("\nPENDING ACTION ITEMS (carry-forward; if someone commits again to the same task in this meeting, they did not complete it on time):")
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

    # mark processing start
    from datetime import datetime

    meeting.status = "processing"
    meeting.processing_stage = "asr"
    meeting.processing_progress = 0
    meeting.processing_started_at = datetime.utcnow()
    meeting.processing_finished_at = None
    meeting.processing_error = None
    db.session.commit()

    # --- ASR ---
    transcript_text = None
    transcript_model = "stub"
    transcript_lang = None

    # 1) Try Deepgram if API key is set (reliable cloud transcription like SMART_MEET_AI)
    deepgram_key = os.environ.get("DEEPGRAM_API_KEY") or getattr(Config, "DEEPGRAM_API_KEY", None)
    if deepgram_key and deepgram_key != "YOUR_DEEPGRAM_API_KEY_HERE":
        try:
            def _asr_progress(done, total):
                pct = int((done / max(total, 1)) * 80)
                meeting.processing_stage = "asr"
                meeting.processing_progress = pct
                db.session.commit()

            meeting.processing_stage = "asr"
            meeting.processing_progress = 5
            db.session.commit()

            asr = transcribe_with_deepgram(
                meeting.audio_path,
                api_key=deepgram_key,
                language=os.environ.get("DEEPGRAM_LANG", "en"),
            )
            transcript_text = asr.text
            transcript_model = asr.model_name
            transcript_lang = asr.language
        except Exception:
            pass  # fall through to whisper or stub

    # 2) Try whisper.cpp if Deepgram not used and model is configured
    if transcript_text is None:
        try:
            def _asr_progress(done, total):
                pct = int((done / max(total, 1)) * 80)
                meeting.processing_stage = "asr"
                meeting.processing_progress = pct
                db.session.commit()

            asr = transcribe_with_whispercpp(
                meeting.audio_path,
                artifacts_dir=Config.ARTIFACTS_DIR,
                output_basename=f"project_{meeting.project_id}_meeting_{meeting.id}",
                model_path=os.environ.get("WHISPER_CPP_MODEL") or Config.WHISPER_CPP_MODEL,
                bin_path=os.environ.get("WHISPER_CPP_BIN") or Config.WHISPER_CPP_BIN,
                language=os.environ.get("WHISPER_CPP_LANG") or Config.WHISPER_CPP_LANG,
                chunk_seconds=300,
                progress_cb=_asr_progress,
            )
            transcript_text = asr.text
            transcript_model = asr.model_name
            transcript_lang = asr.language
        except Exception as e:
            print("Whisper transcription failed:", e)
            transcript_text = (
                "ASR disabled (set DEEPGRAM_API_KEY for cloud transcription, or install ffmpeg + whisper.cpp). "
                "This placeholder keeps the pipeline demo-able."
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
    db.session.commit()

    # Generate segments for manual speaker labeling (only if not already present).
    if not getattr(transcript, "speaker_segments_json", None):
        try:
            transcript.speaker_segments_json = json.dumps(_split_into_segments(transcript_text))
        except Exception:
            transcript.speaker_segments_json = None

    # --- Context memory (project-based): previous summaries + pending action items ---
    context_text = build_context_for_project(meeting.project_id)

    # --- Summarization (Gemini first with context, then BART/fallback) ---
    meeting.processing_stage = "summary"
    meeting.processing_progress = max(meeting.processing_progress or 0, 85)
    db.session.commit()

    summarization_input = "\n\n".join(
        [
            context_text if context_text else "PROJECT CONTEXT: (none)",
            "CURRENT MEETING TRANSCRIPT:",
            transcript_text,
        ]
    )

    use_gemini_decisions_and_actions = False
    extraction = extract_decisions_and_actions(transcript_text)  # default rule-based
    summ = None

    gemini_key = os.environ.get("GEMINI_API_KEY") or getattr(Config, "GEMINI_API_KEY", None)
    if gemini_key and gemini_key != "YOUR_GEMINI_API_KEY_HERE":
        try:
            summ = summarize_with_gemini(context_text=context_text, transcript=transcript_text, api_key=gemini_key)
            use_gemini_decisions_and_actions = True

        except Exception as e:
            print("Gemini summarization failed:", e)
            traceback.print_exc()

    if summ is None:
        try:
            summ = summarize_with_transformers(summarization_input)
        except Exception:
            summ = fallback_summary(summarization_input)

    # --- Extraction: use Gemini's structured output if available, else rule-based ---
    meeting.processing_stage = "extract"
    meeting.processing_progress = 92
    db.session.commit()

    _auto_resolve_action_items_from_transcript(meeting, transcript_text)

    existing_pending = (
        ActionItem.query.filter_by(project_id=meeting.project_id, status="pending")
        .order_by(ActionItem.created_at.asc())
        .all()
    )
    existing_keys = {(_norm(ai.who), _norm(ai.what)) for ai in existing_pending}
    existing_by_key = {(_norm(ai.who), _norm(ai.what)): ai for ai in existing_pending}

    extracted_items_payload: list[dict] = []
    decisions_for_json = extraction.decisions

    if use_gemini_decisions_and_actions and hasattr(summ, "decisions") and hasattr(summ, "action_items"):
        decisions_for_json = summ.decisions
        for item in summ.action_items:
            who = item.get("who")
            will_do = item.get("will_do") or "do"
            what = (item.get("what") or "").strip()
            by_when = item.get("by_when")  # may be date or None
            if not what:
                continue
            key = (_norm(who), _norm(what))
            if key in existing_keys:
                existing_ai = existing_by_key.get(key)
                if existing_ai:
                    existing_ai.last_rementioned_meeting_id = meeting.id
                extracted_items_payload.append({
                    "who": who,
                    "will_do": will_do,
                    "what": what,
                    "by_when": by_when.isoformat() if hasattr(by_when, "isoformat") else by_when,
                    "deduped": True,
                    "rementioned_in_meeting_id": meeting.id,
                })
                continue
            ai = ActionItem(
                project_id=meeting.project_id,
                created_in_meeting_id=meeting.id,
                who=who,
                will_do=will_do,
                what=what,
                by_when=by_when if hasattr(by_when, "isoformat") else None,
                status="pending",
            )
            db.session.add(ai)
            existing_keys.add(key)
            extracted_items_payload.append({
                "who": who,
                "will_do": will_do,
                "what": what,
                "by_when": by_when.isoformat() if hasattr(by_when, "isoformat") else by_when,
            })
    else:
        for item in extraction.action_items:
            key = (_norm(item.who), _norm(item.what))
            if key in existing_keys:
                existing_ai = existing_by_key.get(key)
                if existing_ai:
                    existing_ai.last_rementioned_meeting_id = meeting.id
                extracted_items_payload.append(
                    {
                        "who": item.who,
                        "will_do": item.will_do,
                        "what": item.what,
                        "by_when": item.by_when.isoformat() if item.by_when else None,
                        "deduped": True,
                        "rementioned_in_meeting_id": meeting.id,
                    }
                )
                continue

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
            existing_keys.add(key)
            extracted_items_payload.append(
                {"who": item.who, "will_do": item.will_do, "what": item.what, "by_when": item.by_when.isoformat() if item.by_when else None}
            )

    # --- Summary persistence ---
    summary = Summary.query.filter_by(meeting_id=meeting.id).first()
    decisions_json = json.dumps(decisions_for_json)
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
    meeting.processing_stage = "done"
    meeting.processing_progress = 100
    meeting.processing_finished_at = datetime.utcnow()
    meeting.processing_error = None
    db.session.commit()
    try:
        from ..activity import log_activity
        log_activity(project_id=meeting.project_id, meeting_id=meeting.id, action="meeting_processed")
    except Exception:
        pass
    return meeting

