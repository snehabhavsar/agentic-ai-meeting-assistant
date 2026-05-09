from __future__ import annotations

from datetime import datetime, date

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .db import db


def utcnow() -> datetime:
    return datetime.utcnow()


# ─────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────

class User(db.Model, UserMixin):
    """
    Application user. Each user owns their own projects, meetings, and action items.
    Flask-Login's UserMixin provides is_authenticated, is_active, get_id(), etc.
    """

    __tablename__ = "users"

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(200), nullable=False)
    email        = db.Column(db.String(320), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at   = db.Column(db.DateTime, nullable=False, default=utcnow)

    projects = db.relationship("Project", back_populates="user", cascade="all, delete-orphan", lazy="dynamic")

    # ── password helpers ──────────────────────────────────────
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # ── initials for avatar ───────────────────────────────────
    @property
    def initials(self) -> str:
        parts = (self.name or "U").split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return parts[0][:2].upper()

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "name":       self.name,
            "email":      self.email,
            "initials":   self.initials,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ─────────────────────────────────────────────────────────────
# Project
# ─────────────────────────────────────────────────────────────

class Project(db.Model):
    """
    A project is the top-level container for meetings and project-scoped memory.
    Each project belongs to one user (user_id = NULL for legacy/demo data).
    Project names are unique per-user (enforced at the API layer).
    """

    __tablename__ = "projects"

    id          = db.Column(db.Integer, primary_key=True)
    # user_id is nullable for backward compatibility with pre-auth data.
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    name        = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    participants_json  = db.Column(db.Text, nullable=True)
    name_aliases_json  = db.Column(db.Text, nullable=True)
    archived    = db.Column(db.Boolean, nullable=False, default=False)
    created_at  = db.Column(db.DateTime, nullable=False, default=utcnow)

    user         = db.relationship("User", back_populates="projects")
    meetings     = db.relationship("Meeting",    back_populates="project", cascade="all, delete-orphan")
    action_items = db.relationship("ActionItem", back_populates="project", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        import json

        participants = []
        try:
            participants = json.loads(self.participants_json) if self.participants_json else []
        except Exception:
            participants = []

        name_aliases = {}
        try:
            name_aliases = json.loads(self.name_aliases_json) if self.name_aliases_json else {}
            if not isinstance(name_aliases, dict):
                name_aliases = {}
        except Exception:
            name_aliases = {}

        return {
            "id":                 self.id,
            "user_id":            self.user_id,
            "name":               self.name,
            "description":        self.description,
            "participants_json":  self.participants_json,
            "participants":       participants,
            "name_aliases_json":  self.name_aliases_json,
            "name_aliases":       name_aliases,
            "archived":           getattr(self, "archived", False),
            "created_at":         self.created_at.isoformat() if self.created_at else None,
        }


# ─────────────────────────────────────────────────────────────
# Meeting
# ─────────────────────────────────────────────────────────────

class Meeting(db.Model):
    """A meeting is always linked to exactly one project."""

    __tablename__ = "meetings"

    id         = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)

    title      = db.Column(db.String(250), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at   = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    notes      = db.Column(db.Text, nullable=True)
    audio_path = db.Column(db.Text, nullable=True)

    status             = db.Column(db.String(40),  nullable=False, default="created", index=True)
    processing_error   = db.Column(db.Text,        nullable=True)
    processing_stage   = db.Column(db.String(80),  nullable=True)
    processing_progress = db.Column(db.Integer,    nullable=True)
    processing_started_at  = db.Column(db.DateTime, nullable=True)
    processing_finished_at = db.Column(db.DateTime, nullable=True)

    project    = db.relationship("Project",    back_populates="meetings")
    transcript = db.relationship("Transcript", uselist=False, back_populates="meeting", cascade="all, delete-orphan")
    summary    = db.relationship("Summary",    uselist=False, back_populates="meeting", cascade="all, delete-orphan")

    def to_dict(self, include_children: bool = False) -> dict:
        payload = {
            "id":         self.id,
            "project_id": self.project_id,
            "title":      self.title,
            "started_at": self.started_at.isoformat()  if self.started_at  else None,
            "ended_at":   self.ended_at.isoformat()    if self.ended_at    else None,
            "created_at": self.created_at.isoformat()  if self.created_at  else None,
            "notes":      getattr(self, "notes", None),
            "audio_path": self.audio_path,
            "status":     self.status,
            "processing_error":    self.processing_error,
            "processing_stage":    self.processing_stage,
            "processing_progress": self.processing_progress,
            "processing_started_at":  self.processing_started_at.isoformat()  if self.processing_started_at  else None,
            "processing_finished_at": self.processing_finished_at.isoformat() if self.processing_finished_at else None,
        }
        if include_children:
            payload["transcript"] = self.transcript.to_dict() if self.transcript else None
            payload["summary"]    = self.summary.to_dict()    if self.summary    else None
        return payload


# ─────────────────────────────────────────────────────────────
# Transcript
# ─────────────────────────────────────────────────────────────

class Transcript(db.Model):
    """Stores ASR output for a meeting."""

    __tablename__ = "transcripts"

    id         = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False, unique=True, index=True)

    text                  = db.Column(db.Text,        nullable=False)
    language              = db.Column(db.String(20),  nullable=True)
    model_name            = db.Column(db.String(100), nullable=True)
    speaker_segments_json = db.Column(db.Text,        nullable=True)
    created_at            = db.Column(db.DateTime,    nullable=False, default=utcnow)

    meeting = db.relationship("Meeting", back_populates="transcript")

    def to_dict(self) -> dict:
        segments = []
        try:
            import json
            segments = json.loads(self.speaker_segments_json) if self.speaker_segments_json else []
        except Exception:
            segments = []

        return {
            "id":                    self.id,
            "meeting_id":            self.meeting_id,
            "text":                  self.text,
            "language":              self.language,
            "model_name":            self.model_name,
            "speaker_segments_json": self.speaker_segments_json,
            "speaker_segments":      segments,
            "created_at":            self.created_at.isoformat() if self.created_at else None,
        }


# ─────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────

class Summary(db.Model):
    """Stores structured meeting minutes."""

    __tablename__ = "summaries"

    id          = db.Column(db.Integer, primary_key=True)
    meeting_id  = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False, unique=True, index=True)

    summary_text       = db.Column(db.Text,        nullable=False)
    decisions_json     = db.Column(db.Text,        nullable=True)
    action_items_json  = db.Column(db.Text,        nullable=True)
    model_name         = db.Column(db.String(120), nullable=True)
    created_at         = db.Column(db.DateTime,    nullable=False, default=utcnow)

    meeting = db.relationship("Meeting", back_populates="summary")

    def to_dict(self) -> dict:
        decisions    = []
        action_items = []
        try:
            import json
            decisions    = json.loads(self.decisions_json)    if self.decisions_json    else []
            action_items = json.loads(self.action_items_json) if self.action_items_json else []
        except Exception:
            pass

        return {
            "id":                   self.id,
            "meeting_id":           self.meeting_id,
            "summary_text":         self.summary_text,
            "decisions_json":       self.decisions_json,
            "action_items_json":    self.action_items_json,
            "decisions":            decisions,
            "action_items_extracted": action_items,
            "model_name":           self.model_name,
            "created_at":           self.created_at.isoformat() if self.created_at else None,
        }


# ─────────────────────────────────────────────────────────────
# ActionItem
# ─────────────────────────────────────────────────────────────

class ActionItem(db.Model):
    """
    Project-scoped action item — the core of context retention.
    Format: Who – Will do – What – By when
    """

    __tablename__ = "action_items"

    id         = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)

    created_in_meeting_id      = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=True, index=True)
    resolved_in_meeting_id     = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=True, index=True)
    last_rementioned_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=True, index=True)

    who     = db.Column(db.String(200), nullable=True)
    will_do = db.Column(db.String(200), nullable=True)
    what    = db.Column(db.Text, nullable=False)
    by_when = db.Column(db.Date, nullable=True)

    status     = db.Column(db.String(20),  nullable=False, default="pending", index=True)
    created_at = db.Column(db.DateTime,    nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime,    nullable=False, default=utcnow, onupdate=utcnow)

    project = db.relationship("Project", back_populates="action_items")

    def to_dict(self) -> dict:
        return {
            "id":                          self.id,
            "project_id":                  self.project_id,
            "created_in_meeting_id":       self.created_in_meeting_id,
            "resolved_in_meeting_id":      self.resolved_in_meeting_id,
            "last_rementioned_meeting_id": self.last_rementioned_meeting_id,
            "who":                         self.who,
            "will_do":                     self.will_do,
            "what":                        self.what,
            "by_when":                     self.by_when.isoformat() if isinstance(self.by_when, date) else None,
            "status":                      self.status,
            "created_at":                  self.created_at.isoformat() if self.created_at else None,
            "updated_at":                  self.updated_at.isoformat() if self.updated_at else None,
        }


# ─────────────────────────────────────────────────────────────
# ActivityLog
# ─────────────────────────────────────────────────────────────

class ActivityLog(db.Model):
    """Optional audit trail: meetings processed, action items completed, etc."""

    __tablename__ = "activity_logs"

    id             = db.Column(db.Integer, primary_key=True)
    project_id     = db.Column(db.Integer, db.ForeignKey("projects.id"),    nullable=True, index=True)
    meeting_id     = db.Column(db.Integer, db.ForeignKey("meetings.id"),    nullable=True, index=True)
    action_item_id = db.Column(db.Integer, db.ForeignKey("action_items.id"), nullable=True, index=True)
    action         = db.Column(db.String(120), nullable=False)
    details        = db.Column(db.Text,        nullable=True)
    created_at     = db.Column(db.DateTime,    nullable=False, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id":             self.id,
            "project_id":     self.project_id,
            "meeting_id":     self.meeting_id,
            "action_item_id": self.action_item_id,
            "action":         self.action,
            "details":        self.details,
            "created_at":     self.created_at.isoformat() if self.created_at else None,
        }
