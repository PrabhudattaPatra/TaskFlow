from sqlalchemy.orm import Session

from app.models import Activity, Task, User
from app.schemas import ActivityOut, TaskOut, UserOut


def user_out(u: User | None) -> UserOut | None:
    return UserOut.model_validate(u) if u else None


def task_out(t: Task, with_project: bool = False) -> TaskOut:
    return TaskOut(
        id=t.id,
        project_id=t.project_id,
        project_name=t.project.name if with_project else None,
        title=t.title,
        description=t.description,
        status=t.status,
        priority=t.priority,
        due_date=t.due_date,
        assignee=user_out(t.assignee),
        creator=user_out(t.creator),
        completed_at=t.completed_at,
        created_at=t.created_at,
    )


def activity_out(a: Activity, with_project: bool = False) -> ActivityOut:
    return ActivityOut(
        id=a.id,
        project_id=a.project_id,
        project_name=None,
        type=a.type,
        task_id=a.task_id,
        message=a.message,
        actor=user_out(a.actor),
        created_at=a.created_at,
    )


def log_activity(
    db: Session,
    project_id: int,
    actor: User,
    type_: str,
    message: str,
    task_id: int | None = None,
    target_user_id: int | None = None,
    meta: dict | None = None,
) -> Activity:
    a = Activity(
        project_id=project_id,
        actor_id=actor.id,
        target_user_id=target_user_id,
        type=type_,
        task_id=task_id,
        message=message,
        meta=meta or {},
    )
    db.add(a)
    db.flush()
    a.actor = actor
    return a
