import math
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.deps import get_current_user, require_member
from app.models import Comment, ProjectMember, Task, User
from app.schemas import CommentIn, CommentOut, MoveIn, TaskCreate, TaskOut, TaskPage, TaskUpdate
from app.services.common import activity_out, log_activity, task_out, user_out
from app.ws.manager import hub

router = APIRouter(prefix="/projects/{project_id}", tags=["tasks"])

STATUS_LABEL = {"todo": "To Do", "in_progress": "In Progress", "done": "Done"}
PRIORITY_RANK = case({"low": 1, "medium": 2, "high": 3}, value=Task.priority, else_=0)


# ---------- helpers ----------
def _load_task(db: Session, project_id: int, task_id: int) -> Task:
    t = db.scalar(
        select(Task)
        .where(Task.id == task_id, Task.project_id == project_id)
        .options(joinedload(Task.assignee), joinedload(Task.creator))
    )
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return t


def _check_assignee(db: Session, project_id: int, assignee_id: int) -> User:
    if db.get(ProjectMember, (project_id, assignee_id)) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Assignee must be a member of this project")
    return db.get(User, assignee_id)


def _check_done_permission(task_assignee_id: Optional[int], user: User, m: ProjectMember) -> None:
    if m.role != "owner" and task_assignee_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the task's assignee or the project owner can mark a task as Done"
        )


def _apply_status(t: Task, new_status: str) -> None:
    t.status = new_status
    t.completed_at = datetime.now(timezone.utc) if new_status == "done" else None


def _emit(project_id: int, event_type: str, task: Task, act=None, extra_users: tuple[int, ...] = ()) -> None:
    payload = {
        "type": event_type,
        "project_id": project_id,
        "task": task_out(task).model_dump(mode="json"),
    }
    if act is not None:
        payload["activity"] = activity_out(act).model_dump(mode="json")
    hub.publish_project(project_id, payload)
    for uid in extra_users:
        hub.publish_user(uid, {"type": "assigned.changed", "project_id": project_id, "task_id": task.id})


# ---------- queries ----------
def _filtered(project_id: int, assignee: Optional[str], priority: Optional[str], search: Optional[str], status_: Optional[str]):
    q = select(Task).where(Task.project_id == project_id)
    if assignee:
        if assignee == "unassigned":
            q = q.where(Task.assignee_id.is_(None))
        elif assignee.isdigit():
            q = q.where(Task.assignee_id == int(assignee))
    if priority:
        q = q.where(Task.priority == priority)
    if status_:
        q = q.where(Task.status == status_)
    if search and search.strip():
        q = q.where(Task.title.ilike(f"%{search.strip()}%"))
    return q


@router.get("/tasks", response_model=TaskPage)
def list_tasks(
    project_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    assignee: Optional[str] = Query(None, description="user id or 'unassigned'"),
    priority: Optional[Literal["low", "medium", "high"]] = None,
    status_: Optional[Literal["todo", "in_progress", "done"]] = Query(None, alias="status"),
    search: Optional[str] = None,
    sort_by: Literal["priority", "due_date", "created_at"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    m: ProjectMember = Depends(require_member),
    db: Session = Depends(get_db),
):
    """Backlog view: filtering, search, sorting AND pagination all happen in SQL."""
    base = _filtered(project_id, assignee, priority, search, status_)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    col = {"priority": PRIORITY_RANK, "due_date": Task.due_date, "created_at": Task.created_at}[sort_by]
    primary = col.asc() if order == "asc" else col.desc()
    if sort_by == "due_date":
        primary = primary.nulls_last()  # tasks without a due date always sink to the bottom
    rows = db.scalars(
        base.options(joinedload(Task.assignee), joinedload(Task.creator))
        .order_by(primary, Task.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return TaskPage(
        items=[task_out(t) for t in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )


@router.get("/board", response_model=list[TaskOut])
def board(
    project_id: int,
    assignee: Optional[str] = None,
    priority: Optional[Literal["low", "medium", "high"]] = None,
    search: Optional[str] = None,
    m: ProjectMember = Depends(require_member),
    db: Session = Depends(get_db),
):
    """All tasks for the board columns (filters applied server-side); client groups by status."""
    q = _filtered(project_id, assignee, priority, search, None)
    rows = db.scalars(
        q.options(joinedload(Task.assignee), joinedload(Task.creator)).order_by(PRIORITY_RANK.desc(), Task.id.desc())
    ).all()
    return [task_out(t) for t in rows]


# ---------- mutations ----------
@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(
    project_id: int,
    data: TaskCreate,
    m: ProjectMember = Depends(require_member),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assignee = _check_assignee(db, project_id, data.assignee_id) if data.assignee_id else None
    if data.status == "done":
        _check_done_permission(data.assignee_id, user, m)
    t = Task(
        project_id=project_id,
        title=data.title,
        description=data.description,
        priority=data.priority,
        due_date=data.due_date,
        assignee_id=data.assignee_id,
        created_by=user.id,
    )
    _apply_status(t, data.status)
    db.add(t)
    db.flush()
    t.assignee, t.creator = assignee, user
    act = log_activity(db, project_id, user, "task_created", f'{user.name} created "{t.title}"', task_id=t.id)
    assign_act = None
    if assignee:
        assign_act = log_activity(
            db, project_id, user, "task_assigned", f'{user.name} assigned "{t.title}" to {assignee.name}',
            task_id=t.id, target_user_id=assignee.id,
        )
    db.commit()
    _emit(project_id, "task.created", t, act)
    if assign_act:
        hub.publish_project(project_id, {"type": "activity", "project_id": project_id,
                                         "activity": activity_out(assign_act).model_dump(mode="json")})
        hub.publish_user(assignee.id, {"type": "assigned.changed", "project_id": project_id, "task_id": t.id})
    return task_out(t)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(project_id: int, task_id: int, m: ProjectMember = Depends(require_member), db: Session = Depends(get_db)):
    return task_out(_load_task(db, project_id, task_id))


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(
    project_id: int,
    task_id: int,
    data: TaskUpdate,
    m: ProjectMember = Depends(require_member),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = _load_task(db, project_id, task_id)
    fields = data.model_fields_set
    old_assignee_id, old_status = t.assignee_id, t.status
    new_assignee_id = data.assignee_id if "assignee_id" in fields else old_assignee_id
    new_assignee = None

    if "assignee_id" in fields and new_assignee_id is not None:
        new_assignee = _check_assignee(db, project_id, new_assignee_id)
    new_status = data.status if "status" in fields and data.status else old_status
    if new_status == "done" and old_status != "done":
        _check_done_permission(new_assignee_id, user, m)  # uses the assignee as it will be after this update

    if "title" in fields and data.title:
        t.title = data.title
    if "description" in fields and data.description is not None:
        t.description = data.description
    if "priority" in fields and data.priority:
        t.priority = data.priority
    if "due_date" in fields:
        t.due_date = data.due_date
    if "assignee_id" in fields:
        t.assignee_id = new_assignee_id
        t.assignee = new_assignee
    if new_status != old_status:
        _apply_status(t, new_status)

    acts = []
    if new_status != old_status:
        acts.append(log_activity(
            db, project_id, user, "task_moved",
            f'{user.name} moved "{t.title}" from {STATUS_LABEL[old_status]} to {STATUS_LABEL[new_status]}',
            task_id=t.id))
    if "assignee_id" in fields and new_assignee_id != old_assignee_id:
        msg = (f'{user.name} assigned "{t.title}" to {new_assignee.name}' if new_assignee
               else f'{user.name} unassigned "{t.title}"')
        acts.append(log_activity(db, project_id, user, "task_assigned", msg, task_id=t.id,
                                 target_user_id=new_assignee_id))
    db.commit()

    # Both the previous and the new assignee need their "Assigned to me" view refreshed.
    notify = tuple({u for u in (old_assignee_id, new_assignee_id) if u}) if new_assignee_id != old_assignee_id else ()
    event = "task.moved" if new_status != old_status else "task.updated"
    _emit(project_id, event, t, acts[0] if acts else None, notify)
    for extra in acts[1:]:
        hub.publish_project(project_id, {"type": "activity", "project_id": project_id,
                                         "activity": activity_out(extra).model_dump(mode="json")})
    return task_out(t)


@router.post("/tasks/{task_id}/move", response_model=TaskOut)
def move_task(
    project_id: int,
    task_id: int,
    data: MoveIn,
    m: ProjectMember = Depends(require_member),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_task(project_id, task_id, TaskUpdate(status=data.status), m, user, db)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(
    project_id: int,
    task_id: int,
    m: ProjectMember = Depends(require_member),
    db: Session = Depends(get_db),
):
    t = _load_task(db, project_id, task_id)
    assignee_id = t.assignee_id
    db.delete(t)
    db.commit()
    hub.publish_project(project_id, {"type": "task.deleted", "project_id": project_id, "task_id": task_id})
    if assignee_id:
        hub.publish_user(assignee_id, {"type": "assigned.changed", "project_id": project_id, "task_id": task_id})


# ---------- comments ----------
def _comment_out(c: Comment) -> CommentOut:
    return CommentOut(id=c.id, task_id=c.task_id, body=c.body, author=user_out(c.author), created_at=c.created_at)


@router.get("/tasks/{task_id}/comments", response_model=list[CommentOut])
def list_comments(project_id: int, task_id: int, m: ProjectMember = Depends(require_member), db: Session = Depends(get_db)):
    _load_task(db, project_id, task_id)
    rows = db.scalars(
        select(Comment).where(Comment.task_id == task_id).options(joinedload(Comment.author)).order_by(Comment.created_at)
    ).all()
    return [_comment_out(c) for c in rows]


@router.post("/tasks/{task_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    project_id: int,
    task_id: int,
    data: CommentIn,
    m: ProjectMember = Depends(require_member),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = _load_task(db, project_id, task_id)
    c = Comment(task_id=task_id, author_id=user.id, body=data.body)
    db.add(c)
    db.flush()
    c.author = user
    act = log_activity(db, project_id, user, "comment_added", f'{user.name} commented on "{t.title}"', task_id=t.id)
    db.commit()
    hub.publish_project(
        project_id,
        {"type": "comment.added", "project_id": project_id, "task_id": task_id,
         "comment": _comment_out(c).model_dump(mode="json"),
         "activity": activity_out(act).model_dump(mode="json")},
    )
    return _comment_out(c)
