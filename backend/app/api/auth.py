from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import (
    COOKIE_NAME,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models import User
from app.schemas import APIMessage, LoginIn, RegisterIn, UserOut
from app.services.categories import seed_categories
from app.services.institutions import seed_institutions


router = APIRouter(prefix="/auth", tags=["auth"])


def set_session(response: Response, user: User):
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(user.id),
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
        max_age=7 * 24 * 60 * 60,
    )


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterIn, response: Response, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    user = User(email=email, password_hash=hash_password(payload.password), display_name=payload.display_name)
    db.add(user)
    db.flush()
    seed_categories(db, user.id)
    seed_institutions(db, user.id)
    db.commit()
    set_session(response, user)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    set_session(response, user)
    return user


@router.post("/logout", response_model=APIMessage)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"message": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(user=Depends(get_current_user)):
    return user
