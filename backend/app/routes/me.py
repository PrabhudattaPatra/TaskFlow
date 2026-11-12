from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.deps import get_current_user
from app.models import Activity, Project, ProjectMember, Task, User
from app.schemas import ActivityOut, TaskOut
from app.services.common import activity_out, task_out

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/assigned", response_model=list[TaskOut])
def assigned_to_me(
    include_done: bool = Query(True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tasks assigned to the user across every project they still belong to."""
    q = (
        select(Task)
        .join(ProjectMember, (ProjectMember.project_id == Task.project_id) & (ProjectMember.user_id == user.id))
        .where(Task.assignee_id == user.id)
        .options(joinedload(Task.assignee), joinedload(Task.creator), joinedload(Task.project))
        .order_by(Task.created_at.desc())
    )
    if not include_done:
        q = q.where(Task.status != "done")
    return [task_out(t, with_project=True) for t in db.scalars(q).all()]


@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    my_projects = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)

    project_count = db.scalar(select(func.count()).select_from(ProjectMember).where(ProjectMember.user_id == user.id)) or 0

    by_status = {"todo": 0, "in_progress": 0, "done": 0}
    for status_, n in db.execute(
        select(Task.status, func.count())
        .where(Task.assignee_id == user.id, Task.project_id.in_(my_projects))
        .group_by(Task.status)
    ):
        by_status[status_] = n

    today = datetime.now(timezone.utc).date()
    week_start = datetime.combine(today - timedelta(days=today.weekday()), time.min, tzinfo=timezone.utc)
    completed_this_week = db.scalar(
        select(func.count()).where(
            Task.assignee_id == user.id,
            Task.status == "done",
            Task.completed_at >= week_start,
            Task.project_id.in_(my_projects),
        )
    ) or 0

    busiest = db.execute(
        select(Project.id, Project.name, func.count(Task.id).label("open"))
        .join(Task, (Task.project_id == Project.id) & (Task.status != "done"))
        .where(Project.id.in_(my_projects))
        .group_by(Project.id, Project.name)
        .order_by(func.count(Task.id).desc(), Project.name)
        .limit(1)
    ).first()

    acts = db.scalars(
        select(Activity)
        .where(
            Activity.project_id.in_(my_projects),
            or_(Activity.actor_id == user.id, Activity.target_user_id == user.id),
        )
        .options(joinedload(Activity.actor))
        .order_by(Activity.created_at.desc(), Activity.id.desc())
        .limit(15)
    ).all()
    names = {p.id: p.name for p in db.scalars(select(Project).where(Project.id.in_({a.project_id for a in acts})))}
    recent = []
    for a in acts:
        out = activity_out(a)
        out.project_name = names.get(a.project_id)
        recent.append(out)

    return {
        "project_count": project_count,
        "assigned_by_status": by_status,
        "completed_this_week": completed_this_week,
        "busiest_project": {"id": busiest.id, "name": busiest.name, "open_tasks": busiest.open} if busiest else None,
        "recent_activity": [a.model_dump(mode="json") for a in recent],
    }
