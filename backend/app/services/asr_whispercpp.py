from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from glob import glob


@dataclass
class ASRResult:
    text: str
    language: str | None
    model_name: str


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)


def _ffmpeg_convert_to_wav_16k_mono(input_path: str, output_path: str) -> None:
    """
    Browser recordings are often .webm. Converting to 16kHz mono WAV makes whisper.cpp consistent.
    Requires `ffmpeg` installed.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH. Install ffmpeg to enable ASR.")

    _run(
        [
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
    )


def _ffmpeg_split_wav_into_chunks(wav_path: str, chunks_dir: str, chunk_seconds: int) -> list[str]:
    """
    Split WAV into smaller WAV chunks using ffmpeg segment muxer.
    """
    if chunk_seconds <= 0:
        return [wav_path]
    os.makedirs(chunks_dir, exist_ok=True)
    out_pattern = os.path.join(chunks_dir, "chunk_%03d.wav")
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            wav_path,
            "-f",
            "segment",
            "-segment_time",
            str(chunk_seconds),
            "-c",
            "copy",
            out_pattern,
        ]
    )
    files = sorted(glob(os.path.join(chunks_dir, "chunk_*.wav")))
    return files if files else [wav_path]

def _resolve_whispercpp_bin(explicit: str | None = None) -> str:
    """
    whisper.cpp is usually installed as a CLI binary. Names vary by install method.
    We try common ones; user can override with WHISPER_CPP_BIN.
    """
    if explicit:
        return explicit

    candidates = ["whisper-cli", "whisper-cpp", "whispercpp", "main", "whisper"]
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError(
        "whisper.cpp binary not found. Install whisper.cpp and/or set WHISPER_CPP_BIN to the executable path."
    )


def transcribe_with_whispercpp(
    audio_path: str,
    *,
    artifacts_dir: str,
    output_basename: str,
    model_path: str | None,
    bin_path: str | None,
    language: str | None = None,
    chunk_seconds: int = 0,
    progress_cb=None,
) -> ASRResult:
    """
    Transcribe using whisper.cpp CLI.

    Required:
    - ffmpeg
    - whisper.cpp CLI binary
    - a ggml model file (e.g., ggml-small.bin)
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(audio_path)

    if not model_path:
        raise RuntimeError(
            "WHISPER_CPP_MODEL not set. Point it to your ggml model file (e.g., /path/to/ggml-small.bin)."
        )
    if not os.path.exists(model_path):
        raise FileNotFoundError(model_path)

    os.makedirs(artifacts_dir, exist_ok=True)

    wav_path = os.path.join(artifacts_dir, f"{output_basename}_16k.wav")
    _ffmpeg_convert_to_wav_16k_mono(audio_path, wav_path)

    whisper_bin = _resolve_whispercpp_bin(bin_path)

    chunk_files = _ffmpeg_split_wav_into_chunks(
        wav_path, os.path.join(artifacts_dir, f"{output_basename}_chunks"), chunk_seconds
    )

    texts: list[str] = []
    for i, chunk_path in enumerate(chunk_files, start=1):
        if progress_cb:
            progress_cb(i - 1, len(chunk_files))

        out_prefix = os.path.join(artifacts_dir, f"{output_basename}_part_{i:03d}")
        cmd = [
            whisper_bin,
            "-m",
            model_path,
            "-f",
            chunk_path,
            "-of",
            out_prefix,
            "-otxt",
        ]
        if language:
            cmd += ["-l", language]

        try:
            _run(cmd)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                "whisper.cpp failed. Check that the binary/model are correct.\n"
                f"cmd={' '.join(cmd)}\n"
                f"stdout={e.stdout}\n"
                f"stderr={e.stderr}"
            ) from e

        txt_path = out_prefix + ".txt"
        if not os.path.exists(txt_path):
            raise RuntimeError(f"whisper.cpp did not create expected transcript file: {txt_path}")

        with open(txt_path, "r", encoding="utf-8") as f:
            part = f.read().strip()
        if part:
            texts.append(part)

        if progress_cb:
            progress_cb(i, len(chunk_files))

    text = "\n".join(texts).strip()

    return ASRResult(text=text, language=language, model_name="whisper.cpp")

