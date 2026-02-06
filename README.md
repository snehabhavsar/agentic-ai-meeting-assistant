# Agentic AI System for Project-Based Meeting Intelligence

Web-based system to record meetings (via browser mic), store them under projects, transcribe with Whisper (local), summarize with Transformers, and extract/track action items across meetings.

## Repo structure (high-level)

- `backend/` Flask API + database + processing pipelines
  - `backend/app/` Flask app package (config, models, routes)
  - `backend/app/routes/` API blueprints
- `frontend/` React UI (Phase 2)
- `data/` local dev artifacts (uploads, transcripts, summaries) (created at runtime)

## Phase 1 (this commit)

- Database schema (SQLAlchemy models)
- Flask backend skeleton with stub APIs

## Phase 2 (now)

- Simple web UI served by Flask (`/`) to record from laptop mic and run post-meeting processing
- Project-based context memory: previous summaries + pending action items are pulled during processing
- Optional local ML (Whisper + Transformers) with safe fallbacks if not installed

## Quickstart (backend)

### 1) Create venv + install deps

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional (enable local Whisper + Transformers):

```bash
pip install -r requirements-ml.txt
```

### 2) Run the API

```bash
export FLASK_APP=run.py
export FLASK_ENV=development
python run.py
```

API runs at `http://127.0.0.1:5000`.

### 3) Use the UI

Open `http://127.0.0.1:5000/`:

- Create/select a project
- Start Recording → Stop
- Audio uploads automatically → Processing runs → minutes appear

### 3) Initialize the database (SQLite by default)

On first run, tables are created automatically.

## Notes

- For prototype we use SQLite (`instance/meeting_ai.sqlite`). You can switch to PostgreSQL by setting `DATABASE_URL`.
- Whisper/Transformers are optional. If not installed, the pipeline runs with explainable fallbacks so you can still demo the end-to-end project flow.

