from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SummaryResult:
    summary_text: str
    model_name: str


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

