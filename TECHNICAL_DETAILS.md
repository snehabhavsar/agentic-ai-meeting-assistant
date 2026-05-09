# Meeting AI — Technical Details

This document provides detailed technical information about the **Meeting AI** system for presentations and development reference.

---

## 1. Project Overview

**Meeting AI** is a web-based system for:

- **Recording** meetings via the browser microphone (or uploading existing audio)
- **Storing** recordings under **projects** (project-based organization)
- **Transcribing** audio using cloud (Deepgram) or local (whisper.cpp) ASR
- **Summarizing** with Google Gemini (or fallback / BART when configured)
- **Extracting and tracking** decisions and action items across meetings
- **Using project context**: previous meeting summaries and pending action items are fed into each new meeting’s processing so the system can detect repeated commitments and completed tasks

The system is designed to be **lightweight** and **explainable**: rule-based extraction where possible, optional ML, and clear fallbacks when APIs or local tools are not available.

---

## 2. Architecture

### 2.1 High-Level

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (single-page app: HTML + vanilla JS + CSS)              │
│  - Record / upload audio                                         │
│  - Select project, view meetings, minutes, action items          │
│  - Manual speaker labeling, name corrections, notes              │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP / REST API
┌──────────────────────────────▼──────────────────────────────────┐
│  Flask backend (Python 3)                                        │
│  - REST API (projects, meetings, action items, misc)             │
│  - Post-meeting pipeline: ASR → context → summarization → extract│
│  - SQLite (default) or PostgreSQL                                │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  External / optional                                             │
│  - Deepgram API (transcription)                                  │
│  - Google Gemini API (summarization + structured action items)   │
│  - whisper.cpp + ffmpeg (local ASR)                              │
└─────────────────────────────────────────────────────────────────┘
```

- **Frontend**: Single-page app served by Flask at `/`. No separate React/Vue build; all UI is in `backend/app/templates/index.html` and `backend/app/static/` (app.js, styles.css).
- **Backend**: Flask app factory, blueprints for UI, projects, meetings, action items, misc. Processing runs in-process (optionally in a background thread for async mode).
- **Data**: SQLite by default (`backend/instance/meeting_ai.sqlite`). Can switch to PostgreSQL via `DATABASE_URL`. Uploads and artifacts under `data/` (configurable).

### 2.2 Repository Structure

| Path | Purpose |
|------|--------|
| `backend/` | Flask application |
| `backend/app/` | App package: config, db, models, routes, services |
| `backend/app/config.py` | Configuration (DB, paths, API keys, whisper.cpp) |
| `backend/app/db.py` | SQLAlchemy `db` instance |
| `backend/app/models.py` | SQLAlchemy models (Project, Meeting, Transcript, Summary, ActionItem, ActivityLog) |
| `backend/app/routes/` | Blueprints: ui, projects, meetings, action_items, misc |
| `backend/app/services/` | Processor pipeline, ASR (Deepgram, whisper.cpp), summarizer, action extractor |
| `backend/app/static/` | app.js, styles.css |
| `backend/app/templates/` | index.html (single page) |
| `backend/instance/` | SQLite DB and instance data (created at runtime) |
| `backend/run.py` | Flask entry point |
| `backend/requirements.txt` | Python dependencies (Flask, SQLAlchemy, google-genai, etc.) |
| `data/` | Created at runtime: uploads, artifacts (paths set in config) |
| `run.sh` | One-command runner: venv, install deps, load .env, start server |
| `README.md`, `DEMO_SCRIPT_TWO_MEETINGS.md` | User and demo documentation |

---

## 3. Technology Stack

### 3.1 Backend

| Technology | Version / notes |
|------------|-----------------|
| Python | 3.x |
| Flask | 3.0.2 |
| Flask-CORS | 4.0.0 |
| Flask-SQLAlchemy | 3.1.1 |
| SQLAlchemy | Via Flask-SQLAlchemy (SQLite or PostgreSQL) |
| python-dotenv | 1.0.1 |
| requests | ≥2.28.0 (for Deepgram HTTP API) |
| google-genai | Google Gemini API client |
| reportlab | ≥4.0.0 (optional; not used in current UI after PDF/email removal) |

### 3.2 Frontend

- **HTML5** (single template), **vanilla JavaScript** (no framework), **CSS**.
- **MediaRecorder API** for browser microphone recording (typically WebM/Opus).
- **Fetch API** for all backend calls.

### 3.3 Optional / External

- **Deepgram** (Nova-2): cloud speech-to-text when `DEEPGRAM_API_KEY` is set.
- **Google Gemini** (e.g. gemini-2.5-flash): summarization and structured action items when `GEMINI_API_KEY` is set.
- **whisper.cpp** + **ffmpeg**: local ASR when `WHISPER_CPP_MODEL` (and optionally `WHISPER_CPP_BIN`) are set; ffmpeg used to convert/split audio for whisper.

---

## 4. Database Schema

All entities use **UTC** for timestamps where applicable.

### 4.1 Project

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | |
| name | String(200) NOT NULL UNIQUE | Project name |
| description | Text | Optional |
| participants_json | Text | JSON array of participant names for speaker labeling, e.g. `["Alice","Bob"]` |
| name_aliases_json | Text | JSON object for ASR name corrections, e.g. `{"kagi":"Gargi"}`; used in labels/summaries only |
| archived | Boolean | Default False |
| created_at | DateTime | |

**Relations:** meetings (one-to-many), action_items (one-to-many). Cascade delete.

### 4.2 Meeting

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | |
| project_id | FK(projects.id) | |
| title | String(250) | Optional |
| started_at, ended_at | DateTime | Optional |
| created_at | DateTime | |
| notes | Text | Optional user notes |
| audio_path | Text | Server path to uploaded recording (e.g. under data/uploads) |
| status | String(40) | created → audio_uploaded → processing → processed (or failed) |
| processing_error | Text | Error message if status = failed |
| processing_stage | String(80) | e.g. asr, summary, extract, done |
| processing_progress | Integer | 0–100 |
| processing_started_at, processing_finished_at | DateTime | |

**Relations:** project, transcript (one-to-one), summary (one-to-one). Cascade delete for transcript/summary.

### 4.3 Transcript

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | |
| meeting_id | FK(meetings.id) UNIQUE | |
| text | Text NOT NULL | Full ASR output |
| language | String(20) | e.g. en |
| model_name | String(100) | e.g. deepgram-nova-2, whisper-small |
| speaker_segments_json | Text | JSON array of {idx, speaker, text} for manual speaker labeling |
| created_at | DateTime | |

### 4.4 Summary

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | |
| meeting_id | FK(meetings.id) UNIQUE | |
| summary_text | Text NOT NULL | Main summary / minutes text |
| decisions_json | Text | JSON array of decision objects |
| action_items_json | Text | JSON array of extracted action items (this meeting) |
| model_name | String(120) | e.g. gemini-2.5-flash |
| created_at | DateTime | |

### 4.5 ActionItem

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | |
| project_id | FK(projects.id) | |
| created_in_meeting_id | FK(meetings.id) | Where it was first created |
| resolved_in_meeting_id | FK(meetings.id) | Where it was marked completed (if any) |
| last_rementioned_meeting_id | FK(meetings.id) | If someone committed again to same task (not done on time) |
| who | String(200) | Assignee (optional) |
| will_do | String(200) | Verb, e.g. prepare |
| what | Text NOT NULL | Task description |
| by_when | Date | Optional deadline |
| status | String(20) | pending | completed |
| created_at, updated_at | DateTime | |

**Relations:** project. Action items are **project-scoped** and can be created in one meeting and resolved or re-mentioned in another.

### 4.6 ActivityLog

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | |
| project_id | FK(projects.id) | Optional |
| meeting_id | FK(meetings.id) | Optional |
| action_item_id | FK(action_items.id) | Optional |
| action | String(120) | e.g. meeting_processed, action_completed, project_created |
| details | Text | Optional |
| created_at | DateTime | |

Used for an optional audit trail; not required for core flow.

### 4.7 Migrations

The app uses **SQLite PRAGMA table_info** in `app/__init__.py` to add missing columns on startup (e.g. participants_json, speaker_segments_json, name_aliases_json, processing_*, last_rementioned_meeting_id, archived, notes). No Flask-Migrate; suitable for prototype and demos.

---

## 5. API Reference

Base path for API: **/api**. All JSON request/response unless noted.

### 5.1 Health

- **GET /health** — Returns `{"status":"ok"}`. No /api prefix.

### 5.2 Projects

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/projects | Create project. Body: `{ "name", "description"? }`. Returns 201 + project. |
| GET | /api/projects | List projects. Query: `archived=0|1`. |
| GET | /api/projects/:id/history | Project history: meetings, stats, pending_action_items (with name aliases applied). Query: from, to, status, q. |
| GET | /api/projects/:id/participants | Get project (includes participants). |
| PUT | /api/projects/:id/participants | Set participants. Body: `{ "participants": ["Alice","Bob"] }`. |
| PATCH | /api/projects/:id | Update project. Body: archived?, description?, name_aliases? (object, e.g. {"kagi":"Gargi"}). |
| DELETE | /api/projects/:id | Delete project and cascade (meetings, action items, etc.). |

### 5.3 Meetings

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/meetings/start | Create meeting. Body: `{ "project_id", "title"? }`. Returns 201 + meeting. |
| POST | /api/meetings/:id/stop | Set ended_at, optional title. |
| POST | /api/meetings/:id/upload_audio | Upload recording. Multipart: file field "audio". Saves under data/uploads/project_X/meeting_Y/original.<ext>. |
| GET | /api/meetings/:id/audio | Stream meeting audio file for playback. 404 if no audio. |
| POST | /api/meetings/:id/process | Run post-meeting pipeline (ASR → context → summarization → extraction). Body: `{ "async": true }` default. Returns 202 when async, 200 when sync. |
| GET | /api/meetings/:id | Get meeting with transcript and summary (include_children). |
| PATCH | /api/meetings/:id | Update meeting. Body: notes?, title?. |
| POST | /api/meetings/:id/duplicate | Duplicate meeting (transcript + summary copied). Returns 201. |
| DELETE | /api/meetings/:id | Delete meeting; unlink action item FKs pointing to it. |
| POST | /api/meetings/:id/speaker_segments/generate | Generate segments from transcript text for manual labeling. |
| PATCH | /api/meetings/:id/speaker_segments | Save speaker labels. Body: `{ "speaker_segments": [ {idx, speaker, text}, ... ] }`. |

### 5.4 Action Items

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/projects/:id/action_items | List action items. Query: status (pending|completed). "who" in response uses project name_aliases. |
| POST | /api/projects/:id/action_items | Create action item. Body: what, who?, will_do?, by_when?, created_in_meeting_id?. |
| PATCH | /api/action_items/:id | Update. Body: status?, who?, will_do?, what?, by_when?, resolved_in_meeting_id?. |
| DELETE | /api/action_items/:id | Delete. |
| POST | /api/action_items/bulk_complete | Body: action_item_ids[], resolved_in_meeting_id?. Mark listed pending items completed. |

### 5.5 Misc

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/projects/:id/activity | Activity log for project. Query: limit (default 50, max 200). |
| GET | /api/backup | Download SQLite backup (SQLite only). |

---

## 6. Post-Meeting Processing Pipeline

Invoked by **POST /api/meetings/:id/process**. Steps in order:

### 6.1 ASR (Automatic Speech Recognition)

1. **Deepgram** (if `DEEPGRAM_API_KEY` set): HTTP POST to Deepgram Nova-2; returns single transcript. Preferred when key is present.
2. **whisper.cpp** (if Deepgram not used and `WHISPER_CPP_MODEL` set):  
   - ffmpeg: convert upload to 16 kHz mono WAV; optionally split into chunks.  
   - Run whisper.cpp CLI per chunk; concatenate results.  
   - Requires ffmpeg and whisper.cpp binary (e.g. whisper-cli).
3. **Fallback**: If both fail or are not configured, store a placeholder message so the pipeline still runs (e.g. for demo).

Result: **transcript_text**, **model_name**, **language** stored in **Transcript** (create or update). Segments for speaker labeling are generated from the transcript (sentence or line split).

### 6.2 Context Retrieval

- **build_context_for_project(project_id)** builds a string:
  - Last N (default 5) **meeting summaries** (summary_text only).
  - All **pending action items** for the project (who – what – due).  
- **Name aliases** from project `name_aliases_json` are applied to each action item’s **who** in this context (so Gemini sees “Gargi” not “kagi”).  
- This string is passed to the summarizer as **PROJECT CONTEXT**.

### 6.3 Transcript for Summarization

- If the meeting has **speaker_segments_json** with segments, the pipeline builds a single transcript string as `"SpeakerName: text"` per line.
- **Name aliases** are applied to this string (and to the raw transcript if no segments) so that ASR misrecognitions (e.g. “kagi”) appear as corrected names (e.g. “Gargi”) in the text sent to the summarizer.  
- The **stored** transcript text is **not** modified; only the copy used for summarization and extraction is corrected.

### 6.4 Summarization

1. **Gemini** (if `GEMINI_API_KEY` set):  
   - Prompt includes PROJECT CONTEXT and the (alias-corrected, optionally speaker-labeled) transcript.  
   - Instructions: detect repeated commitments (same person, same/similar task in PENDING ACTION ITEMS) and note in summary; detect reported completions and return in actionItemsReportedCompleted.  
   - Model: e.g. gemini-2.5-flash.  
   - Response: JSON with agenda, keyPoints, actionItems, actionItemsReportedCompleted, decisions, nextSteps, etc.  
   - Parsed into **StructuredSummaryResult** (summary_text, decisions, action_items, action_items_reported_completed).
2. **Transformers (BART)** (if Gemini fails and BART available): summarization only; no structured extraction.
3. **Fallback**: First N characters of transcript or “(empty transcript)”.

Summary text and (when Gemini is used) decisions and action items from Gemini are persisted in **Summary** (decisions_json, action_items_json, model_name).

### 6.5 Action Item Extraction and Deduplication

- **Rule-based extraction** (action_extractor): regex patterns on the (alias-corrected) transcript for “Who will do What by When” etc.; produces decisions list and ExtractedActionItem list. Used when Gemini is not used or for fallback.
- **Gemini action items**: If summarization was done with Gemini, its action_items (and decisions) are used instead of the rule-based ones.
- **Existing pending items**: Load all pending action items for the project; key = normalized (who, what).
- For each extracted item:
  - If (who, what) matches an existing pending item: set that item’s **last_rementioned_meeting_id** to current meeting (repeated commitment); do not create a new row; append to extracted_items_payload with deduped/rementioned flags.
  - Else: create new **ActionItem** (project_id, created_in_meeting_id, who, will_do, what, by_when, status=pending).
- **Reported completed**: If Gemini returned actionItemsReportedCompleted, ** _mark_reported_completed** marks matching pending items as completed and sets resolved_in_meeting_id.
- **Heuristic**: Phrases like “action item 12 completed” in the transcript trigger marking that action item completed (optional, explainable).

### 6.6 Persistence and Status

- **Summary** row created or updated (summary_text, decisions_json, action_items_json, model_name).
- **Meeting** status set to **processed**, processing_stage **done**, progress 100, processing_finished_at set.
- **ActivityLog** entry: meeting_processed.

Processing can run **synchronously** (200) or **asynchronously** (202, background thread). Async avoids long HTTP timeouts for large audio.

---

## 7. Services (Details)

### 7.1 ASR

- **asr_deepgram**: `transcribe_with_deepgram(audio_path, api_key=, language=)` → ASRResult(text, language, model_name). Uses requests to Deepgram REST API; supports .webm, .wav, .mp3, .m4a.
- **asr_whispercpp**: `transcribe_with_whispercpp(audio_path, artifacts_dir, output_basename, model_path, bin_path, language, chunk_seconds, progress_cb)` → ASRResult. Uses ffmpeg for conversion and chunking; runs whisper CLI; concatenates outputs. Binary resolved from PATH or WHISPER_CPP_BIN.

### 7.2 Summarizer

- **summarize_with_gemini(context_text, transcript, api_key)** → StructuredSummaryResult (summary_text, decisions, action_items, key_points, next_steps, action_items_reported_completed). Builds prompt with PROJECT CONTEXT and instructions for repeated commitments and reported completions.
- **summarize_with_transformers** (optional): long-text summarization.
- **fallback_summary**: truncate or placeholder.

### 7.3 Action Extractor

- **extract_decisions_and_actions(transcript_text)** → ExtractionResult(decisions, action_items).  
- Decisions: sentences containing keywords (decided, finalized, we agreed, etc.).  
- Actions: regex patterns for “Who will/to/should do What by When” and “Assign What to Who by When”; loose date parsing (today, tomorrow, ISO, next Monday, etc.).

### 7.4 Processor Helpers

- **_get_name_aliases(project_id)**: Load project name_aliases_json → dict.
- **_apply_name_alias_to_who(who, aliases)**: Case-insensitive key match; return alias value or who.
- **_apply_name_aliases_to_text(text, aliases)**: Replace alias keys with values in text (for summarizer input only).
- **_split_into_segments(transcript_text)**: Split by newlines or sentences → list of {idx, speaker: None, text}.
- **_mark_reported_completed(meeting, reported_list)**: Match reported (who, what) to pending items; set status=completed, resolved_in_meeting_id.
- **_auto_resolve_action_items_from_transcript(meeting, transcript_text)**: Regex “action item N done/completed” → mark those items completed.

---

## 8. Configuration and Environment

### 8.1 Config (backend/app/config.py)

| Key | Default / source | Description |
|-----|------------------|-------------|
| SECRET_KEY | env SECRET_KEY / dev default | Flask secret |
| DATABASE_URL | env | If set, used as SQLALCHEMY_DATABASE_URI (e.g. Postgres). |
| SQLALCHEMY_DATABASE_URI | sqlite in instance/ | Set in app factory if DATABASE_URL not set. |
| DATA_DIR | env or repo_root/data | Parent for uploads and artifacts. |
| UPLOAD_DIR | DATA_DIR/uploads | Meeting audio files. |
| ARTIFACTS_DIR | DATA_DIR/artifacts | e.g. whisper intermediate files. |
| MAX_CONTENT_LENGTH | env or 200MB | Max upload size. |
| WHISPER_CPP_BIN | env | Optional; else auto-detect from PATH. |
| WHISPER_CPP_MODEL | env | Path to ggml model (e.g. ggml-small.bin). |
| WHISPER_CPP_LANG | env | e.g. en, hi. |
| DEEPGRAM_API_KEY | env | Enables Deepgram ASR. |
| DEEPGRAM_LANG | env, default en | Language for Deepgram. |
| GEMINI_API_KEY | env | Enables Gemini summarization and structured extraction. |

### 8.2 .env (optional)

- **DEEPGRAM_API_KEY**, **GEMINI_API_KEY**: Recommended for real transcription and summarization.
- **DEEPGRAM_LANG**: Optional.
- Loaded by `run.sh` from `backend/.env` or repo root `.env`.

### 8.3 run.sh

- Creates/uses **backend/.venv**, installs **requirements.txt**, ensures **backend/instance** exists.
- Loads .env; auto-sets **WHISPER_CPP_MODEL** if `~/models/whisper/ggml-small.bin` exists.
- Default **PORT=5000**; if busy, uses 5001.
- Runs: `flask --app run.py run --debug --port $PORT --no-reload`.

---

## 9. Key Features (Technical Summary)

### 9.1 Project-Based Context Memory

- Each meeting’s summarization receives **previous meeting summaries** and **pending action items** for the same project.
- Enables the model to note “same task committed again” (not done on time) and “task reported completed”.

### 9.2 Speaker Name Corrections (Name Aliases)

- **Project.name_aliases_json**: e.g. `{"kagi":"Gargi"}`.
- Applied: (1) to the transcript **copy** sent to the summarizer (so Gemini outputs correct names); (2) to **who** in context (pending action items); (3) to **who** in all action item API responses. Stored transcript text is unchanged.

### 9.3 Manual Speaker Labeling

- Transcript is split into **segments** (by line or sentence). User can assign **speaker** per segment (from project participants).
- When segments have speakers, the pipeline builds a “Speaker: text” transcript for summarization so the model can attribute actions to the right person. Name aliases still applied.

### 9.4 Audio Playback

- **GET /api/meetings/:id/audio** streams the meeting recording (from meeting.audio_path) with appropriate Content-Type (e.g. audio/webm). UI shows an `<audio controls>` when the meeting has audio_path.

### 9.5 Repeated Commitment Detection

- Implemented in the **Gemini prompt**: if the transcript shows someone committing again to a task that already appears in PENDING ACTION ITEMS (same person, same/similar task), the summary must explicitly note it and the item is linked via **last_rementioned_meeting_id** (deduplication in extraction).

### 9.6 Activity Log

- Optional **ActivityLog** entries for project_created, meeting_processed, action_completed. Exposed via GET /api/projects/:id/activity.

---

## 10. Security and Deployment Notes

- **Secret key**: Set **SECRET_KEY** in production.
- **Database**: Use **DATABASE_URL** (e.g. PostgreSQL) and strong credentials in production.
- **API keys**: Keep **DEEPGRAM_API_KEY** and **GEMINI_API_KEY** in environment or secure secret store; do not commit.
- **Uploads**: Stored on server filesystem; in production consider object storage (e.g. S3) and scanning.
- **CORS**: Flask-CORS is enabled; restrict origins in production.
- **HTTPS**: Use a reverse proxy (e.g. nginx) and TLS in production; run Flask behind it.

---

## 11. How to Run (Recap)

```bash
# From repo root
bash run.sh
# → Server at http://127.0.0.1:5000 (or 5001)
# Open in browser: create project → record or upload → process → view minutes and action items.
```

Optional: set **DEEPGRAM_API_KEY** and **GEMINI_API_KEY** in `backend/.env` for cloud ASR and summarization. For local ASR: install ffmpeg and whisper.cpp, set **WHISPER_CPP_MODEL** (and optionally **WHISPER_CPP_BIN**).

---

## 12. Performance Analysis

### 12.1 Algorithmic Complexity of System Pipeline

**Table 4.15: Algorithmic Complexity of System Pipeline**

| Pipeline Stage | Time Complexity | Description |
|----------------|-----------------|-------------|
| Audio Upload & Storage | O(n) | Saving and reading audio file of size *n* bytes |
| ASR / Transcription (Deepgram or Whisper) | O(n) | Converting audio of duration *n* to transcript text |
| Context Retrieval | O(m + a) | Fetching last *m* meeting summaries and *a* pending action items from the database |
| Prompt Construction | O(k) | Assembling summarisation prompt from context + transcript (*k* = total character/token count) |
| LLM Summarisation (Gemini) | O(p²) | Transformer self-attention over *p* prompt tokens |
| Action Item Extraction | O(t) | Regex pattern matching across *t* transcript sentences |
| Deduplication | O(e + x) | Hash-set lookup over *e* existing pending items and *x* newly extracted items |

The system remains responsive even as the number of stored meetings grows, because context retrieval is bounded by a fixed window (last 5 summaries) and deduplication uses constant-time hash lookups rather than pairwise comparison.

### 12.2 Estimated Codebase Size

**Table 4.16: Estimated Codebase Size**

| System Component | Approximate Lines of Code |
|------------------|--------------------------|
| Backend API (routes, services, config) | ~2,100 |
| Frontend Application (JS, HTML, CSS) | ~2,000 |
| Database Schema (models, db) | ~300 |
| **Total** | **~4,400** |

---

## 13. Test Cases

### 13.1 Core Feature Test Cases (TC-01 to TC-08)

| Test ID | Description | Input | Expected Output | Actual Output | Status |
|---------|-------------|-------|-----------------|---------------|--------|
| TC-01 | Create a new project with a valid name | `POST /api/projects` — `{ "name": "Sprint Planning", "description": "Q2 sprint" }` | HTTP 201; project object returned with `id`, `name`, `status` | HTTP 201; project created and returned | Pass |
| TC-02 | Create a project with a duplicate name | `POST /api/projects` — `{ "name": "Sprint Planning" }` (name already exists) | HTTP 409; `{ "error": "project with this name already exists" }` | HTTP 409; error message returned | Pass |
| TC-03 | Create a project with missing name field | `POST /api/projects` — `{ "description": "no name given" }` | HTTP 400; `{ "error": "name is required" }` | HTTP 400; error message returned | Pass |
| TC-04 | Start a meeting for a valid project | `POST /api/meetings/start` — `{ "project_id": 1, "title": "Daily Standup" }` | HTTP 201; meeting object with `status: "created"` | HTTP 201; meeting created and returned | Pass |
| TC-05 | Start a meeting with a non-existent project ID | `POST /api/meetings/start` — `{ "project_id": 9999 }` | HTTP 404; `{ "error": "invalid project_id" }` | HTTP 404; error returned | Pass |
| TC-06 | Upload an audio file to a meeting | `POST /api/meetings/1/upload_audio` — multipart with `.webm` audio file | HTTP 200; `meeting.status` updated to `"audio_uploaded"`; `audio_path` set | HTTP 200; status updated correctly | Pass |
| TC-07 | Trigger processing on a meeting with no audio | `POST /api/meetings/1/process` — meeting has no audio uploaded | HTTP 400; `{ "error": "no audio uploaded for this meeting" }` | HTTP 400; error returned | Pass |
| TC-08 | Create an action item with missing required field | `POST /api/projects/1/action_items` — `{ "who": "Alice" }` (no `what` field) | HTTP 400; `{ "error": "what is required" }` | HTTP 400; error returned | Pass |

---

*This document reflects the codebase as of the last update. For user-facing quickstart and demo script, see README.md and DEMO_SCRIPT_TWO_MEETINGS.md.*
