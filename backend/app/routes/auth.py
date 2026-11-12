from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import config
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.db.session import get_db
from app.deps import get_current_user
from app.models import RefreshToken, User
from app.schemas import AuthOut, LoginIn, SignupIn, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE = "refresh_token"


def _issue(db: Session, user: User, response: Response) -> AuthOut:
    """Create an access token (returned in body) and a refresh token (httpOnly cookie)."""
    raw, hashed = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hashed,
            expires_at=datetime.now(timezone.utc) + timedelta(days=config.REFRESH_TOKEN_DAYS),
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE,
        raw,
        max_age=config.REFRESH_TOKEN_DAYS * 86400,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        path="/api/auth",
    )
    return AuthOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/signup", response_model=AuthOut, status_code=201)
def signup(data: SignupIn, response: Response, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(name=data.name, email=email, password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    return _issue(db, user, response)


@router.post("/login", response_model=AuthOut)
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return _issue(db, user, response)


@router.post("/refresh", response_model=AuthOut)
def refresh(response: Response, refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    """Rotate the refresh token. Re-use of an already-rotated token revokes the whole family."""
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_token)))
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if row.revoked:
        # Possible token theft: someone replayed a rotated token. Kill every session of this user.
        db.execute(update(RefreshToken).where(RefreshToken.user_id == row.user_id).values(revoked=True))
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token reused; please log in again")
    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    row.revoked = True
    return _issue(db, user, response)


@router.post("/logout", status_code=204)
def logout(response: Response, refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if refresh_token:
        row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_token)))
        if row:
            row.revoked = True
            db.commit()
    response.delete_cookie(COOKIE, path="/api/auth")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
