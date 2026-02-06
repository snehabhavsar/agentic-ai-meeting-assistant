from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date


@dataclass
class ExtractedActionItem:
    who: str | None
    will_do: str | None
    what: str
    by_when: date | None


@dataclass
class ExtractionResult:
    decisions: list[dict]
    action_items: list[ExtractedActionItem]


_ACTION_PATTERNS = [
    # "Alice will prepare slides by 2026-02-10"
    re.compile(
        r"^(?P<who>[A-Z][a-zA-Z]+)\s+will\s+(?P<will_do>[a-zA-Z]+)\s+(?P<what>.+?)(?:\s+by\s+(?P<by>\d{4}-\d{2}-\d{2}))?$",
        re.IGNORECASE,
    ),
    # "Bob to send the email by 2026-02-10"
    re.compile(
        r"^(?P<who>[A-Z][a-zA-Z]+)\s+to\s+(?P<will_do>[a-zA-Z]+)\s+(?P<what>.+?)(?:\s+by\s+(?P<by>\d{4}-\d{2}-\d{2}))?$",
        re.IGNORECASE,
    ),
]


def _parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def extract_decisions_and_actions(transcript_text: str) -> ExtractionResult:
    """
    Rule-based extraction (Phase 2):
    - decisions: sentences containing "decided", "we will", "finalized"
    - actions: simple regex-based patterns

    This is intentionally simple + explainable for viva; we can upgrade later.
    """
    transcript_text = (transcript_text or "").strip()
    if not transcript_text:
        return ExtractionResult(decisions=[], action_items=[])

    # Sentence split: simple punctuation heuristic.
    sentences = re.split(r"(?<=[.!?])\s+", transcript_text)
    decisions: list[dict] = []
    action_items: list[ExtractedActionItem] = []

    for s in sentences:
        s_clean = s.strip()
        if not s_clean:
            continue

        lower = s_clean.lower()
        if any(k in lower for k in ["decided", "finalized", "decision", "we agreed", "we will"]):
            decisions.append({"text": s_clean})

        # Action items
        s_norm = re.sub(r"^\s*[-•]\s*", "", s_clean)  # handle bullet-like lines
        for pat in _ACTION_PATTERNS:
            m = pat.match(s_norm)
            if not m:
                continue
            who = (m.group("who") or "").strip() or None
            will_do = (m.groupdict().get("will_do") or "").strip() or None
            what = (m.groupdict().get("what") or "").strip()
            by_when = _parse_iso_date(m.groupdict().get("by"))
            if what:
                action_items.append(
                    ExtractedActionItem(who=who, will_do=will_do, what=what, by_when=by_when)
                )
            break

    return ExtractionResult(decisions=decisions, action_items=action_items)

