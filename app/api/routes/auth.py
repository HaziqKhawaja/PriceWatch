from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import Token, UserCreate, UserRead
from app.services.auth import authenticate, create_access_token, create_user, get_user_by_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: DbSession):
    conflict = HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
    )
    if get_user_by_email(db, payload.email) is not None:
        raise conflict
    try:
        return create_user(db, payload.email, payload.password, role="user")
    except IntegrityError:
        db.rollback()
        raise conflict from None


@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    user = authenticate(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user))


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser):
    return user
