from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.deps import get_current_user, require_member, require_owner
from app.models import Activity, Project, ProjectMember, Task, User
from app.schemas import ActivityOut, InviteIn, MemberOut, ProjectDetail, ProjectIn, ProjectOut, UserOut
from app.services.common import activity_out, log_activity
from app.ws.manager import hub

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_out(db: Session, p: Project, role: str) -> dict:
    member_count = db.scalar(select(func.count()).select_from(ProjectMember).where(ProjectMember.project_id == p.id))
    open_count = db.scalar(
        select(func.count()).select_from(Task).where(Task.project_id == p.id, Task.status != "done")
    )
    return dict(
        id=p.id,
        name=p.name,
        description=p.description,
        owner_id=p.owner_id,
        created_at=p.created_at,
        my_role=role,
        member_count=member_count or 0,
        open_task_count=open_count or 0,
    )


def _detail(db: Session, p: Project, role: str) -> ProjectDetail:
    members = db.scalars(
        select(ProjectMember)
        .where(ProjectMember.project_id == p.id)
        .options(joinedload(ProjectMember.user))
        .order_by(ProjectMember.joined_at)
    ).all()
    return ProjectDetail(
        **_project_out(db, p, role),
        members=[
            MemberOut(user=UserOut.model_validate(m.user), role=m.role, joined_at=m.joined_at) for m in members
        ],
    )


@router.post("", response_model=ProjectDetail, status_code=201)
def create_project(data: ProjectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = Project(name=data.name, description=data.description, owner_id=user.id)
    p.members.append(ProjectMember(user_id=user.id, role="owner"))
    db.add(p)
    db.commit()
    return _detail(db, p, "owner")


@router.get("", response_model=list[ProjectOut])
def my_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Project, ProjectMember.role)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id)
        .order_by(Project.created_at.desc())
    ).all()
    return [_project_out(db, p, role) for p, role in rows]


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: int, m: ProjectMember = Depends(require_member), db: Session = Depends(get_db)):
    return _detail(db, db.get(Project, project_id), m.role)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, m: ProjectMember = Depends(require_owner), db: Session = Depends(get_db)):
    """FKs are ON DELETE CASCADE: tasks, comments, memberships and activity go with the project."""
    p = db.get(Project, project_id)
    member_ids = list(db.scalars(select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)))
    db.delete(p)
    db.commit()
    for uid in member_ids:
        hub.publish_user(uid, {"type": "project.deleted", "project_id": project_id})
        hub.evict_user(uid, project_id)


@router.post("/{project_id}/members", response_model=ProjectDetail, status_code=201)
def invite_member(
    project_id: int,
    data: InviteIn,
    m: ProjectMember = Depends(require_owner),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invitee = db.scalar(select(User).where(User.email == data.email.lower()))
    if invitee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No registered user with that email")
    if db.get(ProjectMember, (project_id, invitee.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "User is already a member of this project")
    db.add(ProjectMember(project_id=project_id, user_id=invitee.id, role="member"))
    act = log_activity(
        db, project_id, user, "member_invited", f"{user.name} invited {invitee.name}", target_user_id=invitee.id
    )
    db.commit()
    event = {"type": "member.invited", "project_id": project_id, "activity": activity_out(act).model_dump(mode="json")}
    hub.publish_project(project_id, event)
    hub.publish_user(invitee.id, {"type": "project.added", "project_id": project_id})
    return _detail(db, db.get(Project, project_id), "owner")


@router.delete("/{project_id}/members/{user_id}", response_model=ProjectDetail)
def remove_member(
    project_id: int,
    user_id: int,
    m: ProjectMember = Depends(require_owner),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.get(ProjectMember, (project_id, user_id))
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if target.role == "owner":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The project owner cannot be removed")
    removed = db.get(User, user_id)
    # Tasks they created stay (created_by is kept); tasks assigned to them are auto-unassigned.
    db.execute(
        update(Task).where(Task.project_id == project_id, Task.assignee_id == user_id).values(assignee_id=None)
    )
    db.delete(target)
    act = log_activity(
        db, project_id, user, "member_removed", f"{user.name} removed {removed.name}", target_user_id=user_id
    )
    db.commit()
    hub.publish_user(user_id, {"type": "project.removed", "project_id": project_id})
    hub.evict_user(user_id, project_id)
    hub.publish_project(
        project_id,
        {"type": "member.removed", "project_id": project_id, "user_id": user_id,
         "activity": activity_out(act).model_dump(mode="json")},
    )
    return _detail(db, db.get(Project, project_id), "owner")


@router.get("/{project_id}/activity", response_model=list[ActivityOut])
def project_activity(
    project_id: int,
    limit: int = 50,
    m: ProjectMember = Depends(require_member),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    rows = db.scalars(
        select(Activity)
        .where(Activity.project_id == project_id)
        .options(joinedload(Activity.actor))
        .order_by(Activity.created_at.desc(), Activity.id.desc())
        .limit(limit)
    ).all()
    return [activity_out(a) for a in rows]
