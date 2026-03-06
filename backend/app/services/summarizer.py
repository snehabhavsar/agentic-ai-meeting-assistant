from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass
class SummaryResult:
    summary_text: str
    model_name: str


@dataclass
class StructuredSummaryResult(SummaryResult):
    """Result from Gemini with structured decisions and action items."""

    decisions: list[dict]
    action_items: list[dict]
    key_points: list[str] | None = None
    next_steps: list[str] | None = None
    action_items_reported_completed: list[dict] | None = None


def _parse_date_loose(s: str | None) -> date | None:
    if not s or not str(s).strip():
        return None
    raw = str(s).strip().lower()
    if raw in ("not specified", "n/a", "none", ""):
        return None
    today = datetime.utcnow().date()
    if raw == "today":
        return today
    if raw in ("tomorrow", "tmr"):
        return today + timedelta(days=1)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if m:
        try:
            return date.fromisoformat(raw)
        except Exception:
            pass
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", raw)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except Exception:
            pass
    return None


def summarize_with_gemini(
    context_text: str,
    transcript: str,
    api_key: str | None = None,
) -> StructuredSummaryResult:
    """Summarize with Google Gemini using project context from previous meetings."""
    try:
        from google import genai
    except Exception as e:
        raise RuntimeError("google-generativeai not installed. pip install google-generativeai") from e

    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key or key == "YOUR_GEMINI_API_KEY_HERE":
        raise ValueError("GEMINI_API_KEY not configured")


    context_block = ""
    if context_text and context_text.strip():
        context_block = f"""PROJECT CONTEXT (previous meeting summaries and pending action items):
{context_text}

IMPORTANT: If the transcript shows someone committing again to a task that already appears in PENDING ACTION ITEMS above (same person, same or similar task), that means they did NOT complete it on time. In your summary (agenda or additionalNotes), explicitly note this. Still include such items in actionItems so we can link them to the existing pending item.

Also: If someone in the transcript REPORTS HAVING COMPLETED a task from PENDING ACTION ITEMS (e.g. "I have prepared the ppt last week", "Gargi prepared the slides"), add it to "actionItemsReportedCompleted" as array of {{"who": "Name", "what": "task"}} matching the pending item so we can mark it completed. Only include tasks clearly reported as DONE.

"""

    prompt = (
    context_block
    + """Analyze this meeting transcript. Return ONLY a JSON object (no markdown):

{
  "agenda": "Brief main purpose (2-3 sentences)",
  "keyPoints": ["Point 1", "Point 2"],
  "actionItems": [{"task": "Description", "assignee": "Name or Not specified", "deadline": "Date or Not specified"}],
  "actionItemsReportedCompleted": [{"who": "Name", "what": "task reported as done"}],
  "decisions": ["Decision 1", "Decision 2"],
  "nextSteps": ["Step 1", "Step 2"],
  "participants": ["Name 1"],
  "meetingDate": "Date or Not specified",
  "additionalNotes": "Other notes"
}

TRANSCRIPT:
"""
    + transcript
)

    client = genai.Client(api_key=key)

    response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt
)

    summary_text = response.text

    cleaned = summary_text.replace("```json", "").replace("```", "").strip()
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if not json_match:
        return StructuredSummaryResult(
            summary_text=summary_text or "(no content)",
            model_name="gemini-2.0-flash",
            decisions=[],
            action_items=[],
            key_points=[],
            next_steps=[],
            action_items_reported_completed=[],
        )

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return StructuredSummaryResult(
            summary_text=summary_text,
            model_name="gemini-2.0-flash",
            decisions=[],
            action_items=[],
            key_points=[],
            next_steps=[],
            action_items_reported_completed=[],
        )

    agenda = data.get("agenda") or ""
    key_points = data.get("keyPoints") or []
    next_steps = data.get("nextSteps") or []
    decisions = [{"text": t} for t in (data.get("decisions") or []) if t]
    raw_actions = data.get("actionItems") or []
    raw_reported_done = data.get("actionItemsReportedCompleted") or []

    action_items = []
    for item in raw_actions:
        if isinstance(item, dict):
            task = item.get("task") or item.get("what") or ""
            assignee = (item.get("assignee") or item.get("who") or "").strip()
            if assignee.lower() in ("not specified", "n/a", "none", ""):
                assignee = None
            deadline = item.get("deadline") or item.get("by_when")
            by_when = _parse_date_loose(deadline)
            action_items.append({
                "who": assignee or None,
                "will_do": "do",
                "what": task,
                "by_when": by_when,
            })

    summary_display = agenda
    if key_points:
        summary_display += "\n\nKey points: " + "; ".join(key_points[:5])

    return StructuredSummaryResult(
        summary_text=summary_display.strip() or agenda,
        model_name="gemini-2.0-flash",
        decisions=decisions,
        action_items=action_items,
        key_points=key_points,
        next_steps=next_steps,
        action_items_reported_completed=[
            {"who": (x.get("who") or "").strip() or None, "what": (x.get("what") or "").strip()}
            for x in raw_reported_done if isinstance(x, dict) and (x.get("what") or "").strip()
        ],
    )


def summarize_with_transformers(text: str, model_name: str = "facebook/bart-large-cnn") -> SummaryResult:
    """
    Local summarization via Hugging Face Transformers.

    For academic prototype:
    - Keep it simple and explainable.
    - Truncate input to avoid max-length issues.
    """
    try:
        from transformers import pipeline  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Transformers not installed. Install backend/requirements-ml.txt to enable summarization."
        ) from e

    # Very simple truncation (character-based). Later we can do token-based truncation.
    max_chars = 8000
    text_in = text.strip()
    if len(text_in) > max_chars:
        text_in = text_in[:max_chars] + "\n[TRUNCATED]"

    summarizer = pipeline("summarization", model=model_name)
    out = summarizer(text_in, max_length=200, min_length=60, do_sample=False)
    summary_text = (out[0].get("summary_text") or "").strip()

    return SummaryResult(summary_text=summary_text, model_name=model_name)


def fallback_summary(text: str) -> SummaryResult:
    """
    No-ML fallback so the system stays runnable without heavyweight installs.
    """
    text = (text or "").strip()
    if not text:
        return SummaryResult(summary_text="(empty transcript)", model_name="fallback")

    # Naive "summary": first ~3 sentences / 600 chars
    snippet = text[:600]
    return SummaryResult(summary_text=snippet, model_name="fallback")

