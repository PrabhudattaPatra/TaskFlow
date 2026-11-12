import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import ProjectMember, User

bearer = HTTPBearer(auto_error=False)


def _unauth(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None:
        raise _unauth("Not authenticated")
    try:
        user_id = decode_access_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise _unauth("Access token expired")
    except jwt.PyJWTError:
        raise _unauth("Invalid token")
    user = db.get(User, user_id)
    if user is None:
        raise _unauth("User no longer exists")
    return user


def get_membership(db: Session, project_id: int, user_id: int) -> ProjectMember | None:
    return db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
    )


def require_member(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProjectMember:
    """Non-members get 404 so project existence is not leaked."""
    m = get_membership(db, project_id, user.id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return m


def require_owner(m: ProjectMember = Depends(require_member)) -> ProjectMember:
    if m.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the project owner can do this")
    return m
