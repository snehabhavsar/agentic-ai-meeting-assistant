from __future__ import annotations

from datetime import datetime, date

from .db import db


def utcnow() -> datetime:
    # Using a function (not datetime.utcnow()) so SQLAlchemy calls it at row creation time.
    return datetime.utcnow()


class Project(db.Model):
    """
    A project is the top-level container for meetings and project-scoped memory.
    """

    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    # Lightweight participant storage for manual speaker labeling (viva-friendly).
    # Stored as JSON string: ["Alice", "Bob", ...]
    participants_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    meetings = db.relationship("Meeting", back_populates="project", cascade="all, delete-orphan")
    action_items = db.relationship("ActionItem", back_populates="project", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        participants = None
        try:
            import json

            participants = json.loads(self.participants_json) if self.participants_json else []
        except Exception:
            participants = None

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "participants_json": self.participants_json,
            "participants": participants,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Meeting(db.Model):
    """
    A meeting is always linked to exactly one project.
    Audio upload and processing artifacts belong to the meeting.
    """

    __tablename__ = "meetings"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)

    title = db.Column(db.String(250), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    # File system path (prototype). In production you'd likely use object storage.
    audio_path = db.Column(db.Text, nullable=True)

    # status: created -> audio_uploaded -> processed (or failed)
    status = db.Column(db.String(40), nullable=False, default="created", index=True)
    processing_error = db.Column(db.Text, nullable=True)
    processing_stage = db.Column(db.String(80), nullable=True)  # e.g. "asr", "summary"
    processing_progress = db.Column(db.Integer, nullable=True)  # 0..100
    processing_started_at = db.Column(db.DateTime, nullable=True)
    processing_finished_at = db.Column(db.DateTime, nullable=True)

    project = db.relationship("Project", back_populates="meetings")
    transcript = db.relationship("Transcript", uselist=False, back_populates="meeting", cascade="all, delete-orphan")
    summary = db.relationship("Summary", uselist=False, back_populates="meeting", cascade="all, delete-orphan")

    def to_dict(self, include_children: bool = False) -> dict:
        payload = {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "audio_path": self.audio_path,
            "status": self.status,
            "processing_error": self.processing_error,
            "processing_stage": self.processing_stage,
            "processing_progress": self.processing_progress,
            "processing_started_at": self.processing_started_at.isoformat() if self.processing_started_at else None,
            "processing_finished_at": self.processing_finished_at.isoformat() if self.processing_finished_at else None,
        }
        if include_children:
            payload["transcript"] = self.transcript.to_dict() if self.transcript else None
            payload["summary"] = self.summary.to_dict() if self.summary else None
        return payload


class Transcript(db.Model):
    """
    Stores ASR output for a meeting.
    """

    __tablename__ = "transcripts"

    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False, unique=True, index=True)

    text = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(20), nullable=True)
    model_name = db.Column(db.String(100), nullable=True)  # e.g. "whisper-small"
    # Manual speaker labeling (segments) stored as JSON string:
    # [{ "idx": 1, "speaker": "Alice", "text": "..." }, ...]
    speaker_segments_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    meeting = db.relationship("Meeting", back_populates="transcript")

    def to_dict(self) -> dict:
        segments = None
        try:
            import json

            segments = json.loads(self.speaker_segments_json) if self.speaker_segments_json else []
        except Exception:
            segments = None

        return {
            "id": self.id,
            "meeting_id": self.meeting_id,
            "text": self.text,
            "language": self.language,
            "model_name": self.model_name,
            "speaker_segments_json": self.speaker_segments_json,
            "speaker_segments": segments,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Summary(db.Model):
    """
    Stores structured meeting minutes. For explainability, we keep raw JSON strings
    for decisions and action_items_extracted (prototype).

    In later phases we can normalize decisions into their own table if needed.
    """

    __tablename__ = "summaries"

    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False, unique=True, index=True)

    summary_text = db.Column(db.Text, nullable=False)
    decisions_json = db.Column(db.Text, nullable=True)  # JSON string
    action_items_json = db.Column(db.Text, nullable=True)  # JSON string (extracted in this meeting)
    model_name = db.Column(db.String(120), nullable=True)  # e.g. "facebook/bart-large-cnn"
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    meeting = db.relationship("Meeting", back_populates="summary")

    def to_dict(self) -> dict:
        # Expose parsed JSON for UI convenience, but keep original strings too.
        decisions = None
        action_items = None
        try:
            import json

            decisions = json.loads(self.decisions_json) if self.decisions_json else []
            action_items = json.loads(self.action_items_json) if self.action_items_json else []
        except Exception:
            decisions = None
            action_items = None

        return {
            "id": self.id,
            "meeting_id": self.meeting_id,
            "summary_text": self.summary_text,
            "decisions_json": self.decisions_json,
            "action_items_json": self.action_items_json,
            "decisions": decisions,
            "action_items_extracted": action_items,
            "model_name": self.model_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ActionItem(db.Model):
    """
    Project-scoped action items are the key for context retention:
    - they belong to a project
    - they are created in a meeting
    - they may be resolved in a later meeting

    Format required:
      Who – Will do – What – By when
    """

    __tablename__ = "action_items"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)

    created_in_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=True, index=True)
    resolved_in_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=True, index=True)

    who = db.Column(db.String(200), nullable=True)
    will_do = db.Column(db.String(200), nullable=True)
    what = db.Column(db.Text, nullable=False)
    by_when = db.Column(db.Date, nullable=True)

    status = db.Column(db.String(20), nullable=False, default="pending", index=True)  # pending/completed
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    project = db.relationship("Project", back_populates="action_items")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "created_in_meeting_id": self.created_in_meeting_id,
            "resolved_in_meeting_id": self.resolved_in_meeting_id,
            "who": self.who,
            "will_do": self.will_do,
            "what": self.what,
            "by_when": self.by_when.isoformat() if isinstance(self.by_when, date) else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

