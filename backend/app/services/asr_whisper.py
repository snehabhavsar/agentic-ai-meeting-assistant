from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass
class ASRResult:
    text: str
    language: str | None
    model_name: str


def _ffmpeg_convert_to_wav(input_path: str, output_path: str) -> None:
    """
    Whisper relies on ffmpeg for decoding. Some environments handle .webm directly,
    but converting to WAV makes behavior more predictable for demos.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-ac",
        "1",
        "-ar",
        "16000",
        output_path,
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def transcribe_with_whisper(audio_path: str, model_size: str = "small") -> ASRResult:
    """
    Local Whisper ASR.

    - Requires `openai-whisper` + `torch`
    - Requires `ffmpeg` in PATH
    """
    try:
        import whisper  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Whisper not installed. Install backend/requirements-ml.txt to enable ASR."
        ) from e

    if not os.path.exists(audio_path):
        raise FileNotFoundError(audio_path)

    # Convert to wav next to the audio file (for reproducibility in viva).
    wav_path = os.path.splitext(audio_path)[0] + "_16k.wav"
    try:
        _ffmpeg_convert_to_wav(audio_path, wav_path)
        input_for_whisper = wav_path
    except Exception:
        # If ffmpeg isn't available, try whisper direct decode.
        input_for_whisper = audio_path

    model = whisper.load_model(model_size)
    result = model.transcribe(input_for_whisper)

    return ASRResult(
        text=(result.get("text") or "").strip(),
        language=result.get("language"),
        model_name=f"whisper-{model_size}",
    )

