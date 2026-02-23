from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta


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
        r"^(?P<who>[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+will\s+(?P<will_do>[a-zA-Z]+)\s+(?P<what>.+?)(?:\s+by\s+(?P<by>.+))?$",
        re.IGNORECASE,
    ),
    # "Bob to send the email by 2026-02-10"
    re.compile(
        r"^(?P<who>[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+to\s+(?P<will_do>[a-zA-Z]+)\s+(?P<what>.+?)(?:\s+by\s+(?P<by>.+))?$",
        re.IGNORECASE,
    ),
    # "Alice should prepare slides by next Monday"
    re.compile(
        r"^(?P<who>[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+should\s+(?P<will_do>[a-zA-Z]+)\s+(?P<what>.+?)(?:\s+by\s+(?P<by>.+))?$",
        re.IGNORECASE,
    ),
    # "Assign prepare slides to Alice by 2026-02-10"
    re.compile(
        r"^assign\s+(?P<what>.+?)\s+to\s+(?P<who>[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)(?:\s+by\s+(?P<by>.+))?$",
        re.IGNORECASE,
    ),
]


def _parse_date_loose(s: str | None) -> date | None:
    """
    Lightweight date parsing (no heavy deps):
    Supports:
    - 2026-02-16
    - 16/02/2026 or 16-02-2026
    - today, tomorrow
    - in N days
    - next <weekday>
    """
    if not s:
        return None
    raw = s.strip().lower()
    if not raw:
        return None

    today = datetime.utcnow().date()

    if raw in {"today"}:
        return today
    if raw in {"tomorrow", "tmr"}:
        return today + timedelta(days=1)

    m = re.match(r"^in\s+(\d+)\s+days?$", raw)
    if m:
        return today + timedelta(days=int(m.group(1)))

    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if m:
        try:
            return date.fromisoformat(raw)
        except Exception:
            return None

    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", raw)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except Exception:
            return None

    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    m = re.match(r"^next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$", raw)
    if m:
        target = weekdays[m.group(1)]
        delta = (target - today.weekday()) % 7
        delta = 7 if delta == 0 else delta
        return today + timedelta(days=delta)

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
        if any(k in lower for k in ["decided", "finalized", "decision", "we agreed", "we will", "let's", "lets "]):
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
            by_when = _parse_date_loose(m.groupdict().get("by"))
            if what:
                action_items.append(
                    ExtractedActionItem(who=who, will_do=will_do, what=what, by_when=by_when)
                )
            break

    return ExtractionResult(decisions=decisions, action_items=action_items)

