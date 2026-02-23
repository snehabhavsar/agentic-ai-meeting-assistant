#!/usr/bin/env bash
set -euo pipefail

# One-command runner for the viva demo.
# - Creates/uses backend/.venv
# - Installs Python deps (lightweight)
# - Ensures SQLite instance directory exists
# - Enables whisper.cpp ASR automatically if ggml-small.bin is present
# - Picks a free port if 5000 is already in use

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

echo "==> Starting Meeting AI (lightweight)…"
cd "$BACKEND_DIR"

if [[ ! -d ".venv" ]]; then
  echo "==> Creating virtualenv (.venv)…"
  python3 -m venv .venv
fi

echo "==> Activating venv…"
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing Python deps (requirements.txt)…"
pip install -r requirements.txt >/dev/null

echo "==> Ensuring SQLite folder exists (backend/instance)…"
mkdir -p instance

# Auto-enable whisper.cpp if model exists at the common location.
DEFAULT_MODEL="$HOME/models/whisper/ggml-small.bin"
if [[ -z "${WHISPER_CPP_MODEL:-}" && -f "$DEFAULT_MODEL" ]]; then
  export WHISPER_CPP_MODEL="$DEFAULT_MODEL"
  echo "==> Found whisper.cpp model: $WHISPER_CPP_MODEL"
fi

# Optional language default (can override before running: WHISPER_CPP_LANG=hi ./run.sh)
export WHISPER_CPP_LANG="${WHISPER_CPP_LANG:-en}"

PORT="${PORT:-5000}"
if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "==> Port $PORT is busy. Switching to 5001."
    PORT="5001"
  fi
fi

echo "==> Running server on http://127.0.0.1:$PORT/"
echo "    (Ctrl+C to stop)"
echo

# Use flask runner so we can control port + disable reloader (avoids double background jobs).
flask --app run.py run --debug --port "$PORT" --no-reload

