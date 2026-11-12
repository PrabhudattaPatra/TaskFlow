"""Seed demo data. Safe to re-run: wipes only the demo users' data.

Logins (password for both: Password123):
  alice@example.com  (owner of the shared project)
  bob@example.com    (member; has a task assigned to him)
"""
from datetime import date, timedelta

from sqlalchemy import delete, select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Activity, Comment, Project, ProjectMember, Task, User

PASSWORD = "Password123"


def main() -> None:
    with SessionLocal() as db:
        emails = ["alice@example.com", "bob@example.com"]
        old = db.scalars(select(User).where(User.email.in_(emails))).all()
        if old:
            ids = [u.id for u in old]
            for p in db.scalars(select(Project).where(Project.owner_id.in_(ids))):
                db.delete(p)
            db.flush()
            db.execute(delete(User).where(User.id.in_(ids)))
            db.commit()

        alice = User(name="Alice Johnson", email=emails[0], password_hash=hash_password(PASSWORD))
        bob = User(name="Bob Smith", email=emails[1], password_hash=hash_password(PASSWORD))
        db.add_all([alice, bob])
        db.flush()

        p = Project(name="Website Redesign", description="Shared demo project", owner_id=alice.id)
        p.members = [ProjectMember(user_id=alice.id, role="owner"), ProjectMember(user_id=bob.id, role="member")]
        db.add(p)
        db.flush()

        today = date.today()
        tasks = [
            Task(project_id=p.id, title="Design landing page", status="in_progress", priority="high",
                 due_date=today + timedelta(days=3), assignee_id=bob.id, created_by=alice.id),
            Task(project_id=p.id, title="Set up CI pipeline", status="todo", priority="medium",
                 due_date=today + timedelta(days=7), assignee_id=alice.id, created_by=alice.id),
            Task(project_id=p.id, title="Write copy for pricing page", status="todo", priority="low",
                 created_by=bob.id),
            Task(project_id=p.id, title="Choose color palette", status="done", priority="medium",
                 assignee_id=alice.id, created_by=alice.id),
        ]
        db.add_all(tasks)
        db.flush()
        tasks[3].completed_at = tasks[3].created_at
        db.add(Comment(task_id=tasks[0].id, author_id=alice.id, body="Bob, please start with the hero section."))
        db.add_all([
            Activity(project_id=p.id, actor_id=alice.id, type="task_created",
                     task_id=tasks[0].id, message='Alice Johnson created "Design landing page"'),
            Activity(project_id=p.id, actor_id=alice.id, type="task_assigned", task_id=tasks[0].id,
                     target_user_id=bob.id, message='Alice Johnson assigned "Design landing page" to Bob Smith'),
        ])
        db.commit()
        print("Seeded. Log in as alice@example.com or bob@example.com with password", PASSWORD)


if __name__ == "__main__":
    main()
