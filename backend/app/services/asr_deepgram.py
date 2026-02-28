"""
Optional ASR via Deepgram REST API.
When DEEPGRAM_API_KEY is set, use this for reliable cloud transcription
(instead of or before whisper.cpp). Same interface as asr_whispercpp.ASRResult.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from ..config import Config


@dataclass
class ASRResult:
    text: str
    language: str | None
    model_name: str


def transcribe_with_deepgram(
    audio_path: str,
    *,
    api_key: str | None = None,
    language: str = "en",
) -> ASRResult:
    """
    Transcribe audio file using Deepgram Nova-2 REST API.
    Requires: DEEPGRAM_API_KEY set, requests installed.
    """
    import requests

    key = (api_key or os.environ.get("DEEPGRAM_API_KEY") or getattr(Config, "DEEPGRAM_API_KEY", None))
    if not key or key == "YOUR_DEEPGRAM_API_KEY_HERE":
        raise ValueError("DEEPGRAM_API_KEY not configured")

    if not os.path.exists(audio_path):
        raise FileNotFoundError(audio_path)

    with open(audio_path, "rb") as f:
        audio_data = f.read()

    # Determine content type from extension
    ext = os.path.splitext(audio_path)[1].lower()
    content_type = {
        ".webm": "audio/webm",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
    }.get(ext, "audio/webm")

    url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&punctuate=true&language=" + language
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Token {key}",
            "Content-Type": content_type,
        },
        data=audio_data,
        timeout=120,
    )

    if not resp.ok:
        raise RuntimeError(f"Deepgram API error: {resp.status_code} - {resp.text}")

    data = resp.json()
    channels = (data.get("results") or {}).get("channels") or []
    transcript = ""
    if channels:
        alts = (channels[0].get("alternatives") or [{}])
        if alts:
            transcript = alts[0].get("transcript") or ""
    transcript = (transcript or "").strip()

    transcript = (transcript or "").strip()
    if not transcript:
        transcript = "No speech detected in recording."

    return ASRResult(text=transcript, language=language, model_name="deepgram-nova-2")
