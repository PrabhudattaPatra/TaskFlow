import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

Status = Literal["todo", "in_progress", "done"]
Priority = Literal["low", "medium", "high"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class SignupIn(BaseModel):
    name: str
    email: EmailStr
    password: str

    @field_validator("name")
    @classmethod
    def name_ok(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 100:
            raise ValueError("Name is too long")
        return v

    @field_validator("password")
    @classmethod
    def password_rules(cls, v: str) -> str:
        # Documented rule: >= 8 chars, at least one letter and one digit.
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 72:
            raise ValueError("Password must be at most 72 characters")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must contain at least one letter and one number")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: int
    name: str
    email: str


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- projects ----------
class ProjectIn(BaseModel):
    name: str
    description: str = ""

    @field_validator("name")
    @classmethod
    def name_ok(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Project name is required")
        return v


class MemberOut(BaseModel):
    user: UserOut
    role: str
    joined_at: datetime


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    owner_id: int
    created_at: datetime
    my_role: str
    member_count: int
    open_task_count: int = 0


class ProjectDetail(ProjectOut):
    members: list[MemberOut]


class InviteIn(BaseModel):
    email: EmailStr


# ---------- tasks ----------
class TaskCreate(BaseModel):
    title: str
    description: str = ""
    status: Status = "todo"
    priority: Priority = "medium"
    due_date: Optional[date] = None
    assignee_id: Optional[int] = None

    @field_validator("title")
    @classmethod
    def title_ok(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be empty")
        if len(v) > 200:
            raise ValueError("Title must be at most 200 characters")
        return v

    @field_validator("due_date")
    @classmethod
    def due_not_past(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v < date.today():
            raise ValueError("Due date cannot be in the past")
        return v


class TaskUpdate(BaseModel):
    """Partial update: only fields present in the request body are changed."""

    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Status] = None
    priority: Optional[Priority] = None
    due_date: Optional[date] = None
    assignee_id: Optional[int] = None

    @field_validator("title")
    @classmethod
    def title_ok(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be empty")
        if len(v) > 200:
            raise ValueError("Title must be at most 200 characters")
        return v


class MoveIn(BaseModel):
    status: Status


class TaskOut(BaseModel):
    id: int
    project_id: int
    project_name: Optional[str] = None
    title: str
    description: str
    status: str
    priority: str
    due_date: Optional[date]
    assignee: Optional[UserOut]
    creator: Optional[UserOut]
    completed_at: Optional[datetime]
    created_at: datetime


class TaskPage(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int
    pages: int


class CommentIn(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def body_ok(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Comment cannot be empty")
        if len(v) > 2000:
            raise ValueError("Comment is too long")
        return v


class CommentOut(BaseModel):
    id: int
    task_id: int
    body: str
    author: Optional[UserOut]
    created_at: datetime


class ActivityOut(BaseModel):
    id: int
    project_id: int
    project_name: Optional[str] = None
    type: str
    task_id: Optional[int]
    message: str
    actor: Optional[UserOut]
    created_at: datetime
