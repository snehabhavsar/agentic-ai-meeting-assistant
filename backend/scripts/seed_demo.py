"""
Seed demo data for viva.

Usage:
  cd backend
  source .venv/bin/activate
  python scripts/seed_demo.py
"""

from __future__ import annotations

import json

from app import create_app
from app.db import db
from app.models import ActionItem, Meeting, Project, Summary, Transcript


def main() -> None:
    app = create_app()
    with app.app_context():
        # Create a demo project (id stable if empty DB).
        project = Project.query.filter_by(name="Demo Project").first()
        if not project:
            project = Project(
                name="Demo Project",
                description="Seeded project showing context retention across meetings.",
                participants_json=json.dumps(["Alice", "Bob", "Mentor"]),
            )
            db.session.add(project)
            db.session.commit()

        # Meeting 1
        m1 = Meeting.query.filter_by(project_id=project.id, title="Kickoff").first()
        if not m1:
            m1 = Meeting(project_id=project.id, title="Kickoff", status="processed")
            db.session.add(m1)
            db.session.commit()

            t1 = Transcript(
                meeting_id=m1.id,
                text="Alice will prepare slides by tomorrow. We decided to target a prototype by next Monday.",
                model_name="seed",
                speaker_segments_json=json.dumps(
                    [
                        {"idx": 1, "speaker": "Alice", "text": "I will prepare slides by tomorrow."},
                        {"idx": 2, "speaker": "Mentor", "text": "We decided to target a prototype by next Monday."},
                    ]
                ),
            )
            db.session.add(t1)

            s1 = Summary(
                meeting_id=m1.id,
                summary_text="Kickoff completed. Target: prototype by next Monday.",
                decisions_json=json.dumps([{"text": "Prototype target: next Monday."}]),
                action_items_json=json.dumps(
                    [{"who": "Alice", "will_do": "prepare", "what": "slides", "by_when": None}]
                ),
                model_name="seed",
            )
            db.session.add(s1)

            ai1 = ActionItem(
                project_id=project.id,
                created_in_meeting_id=m1.id,
                who="Alice",
                will_do="prepare",
                what="Slides for kickoff follow-up",
                status="pending",
            )
            db.session.add(ai1)
            db.session.commit()

        # Meeting 2
        m2 = Meeting.query.filter_by(project_id=project.id, title="Review").first()
        if not m2:
            m2 = Meeting(project_id=project.id, title="Review", status="processed")
            db.session.add(m2)
            db.session.commit()

            t2 = Transcript(
                meeting_id=m2.id,
                text="Action item 1 completed. Bob will draft the report by 2026-03-01.",
                model_name="seed",
            )
            db.session.add(t2)

            s2 = Summary(
                meeting_id=m2.id,
                summary_text="Reviewed progress. Slides completed. New task: report draft.",
                decisions_json=json.dumps([{"text": "Slides marked completed."}]),
                action_items_json=json.dumps(
                    [{"who": "Bob", "will_do": "draft", "what": "the report", "by_when": "2026-03-01"}]
                ),
                model_name="seed",
            )
            db.session.add(s2)
            db.session.commit()

        print(f"Seeded project id={project.id}. Open UI and select 'Demo Project'.")


if __name__ == "__main__":
    main()

