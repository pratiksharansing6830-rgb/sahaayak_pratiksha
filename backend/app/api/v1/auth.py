from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import (
    DUMMY_HASH, create_access_token, hash_password, verify_password,
)
from app.models import Role, User
from app.schemas.auth import RegisterRequest, TokenResponse, UserOut
from app.services.audit import log_event

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        phone=payload.phone,
        role=Role.CITIZEN,  # public sign-up is always a citizen
    )
    db.add(user)
    try:
        db.flush()
        log_event(db, actor=user, action="USER_REGISTERED", entity_type="user", entity_id=user.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == form.username.strip().lower()))
    password_ok = verify_password(form.password, user.password_hash if user else DUMMY_HASH)

    if user is None or not password_ok or not user.is_active:
        log_event(db, actor=None, action="LOGIN_FAILED", entity_type="user")  # no email stored
        db.commit()
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    log_event(db, actor=user, action="LOGIN_SUCCEEDED", entity_type="user", entity_id=user.id)
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # JWTs are stateless: the client discards the token. We record the event.
    log_event(db, actor=user, action="LOGOUT", entity_type="user", entity_id=user.id)
    db.commit()