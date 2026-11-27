from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User

ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(user: User, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    delta = expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    claims = {
        "sub": str(user.id),
        "role": user.role,
        "exp": datetime.now(UTC) + delta,
    }
    return jwt.encode(claims, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Return the token claims; raises jwt.InvalidTokenError (incl. expiry) if invalid."""
    return jwt.decode(
        token,
        get_settings().JWT_SECRET,
        algorithms=[ALGORITHM],
        options={"require": ["exp", "sub"]},
    )


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(db: Session, email: str, password: str, role: str = "user") -> User:
    user = User(
        email=email.strip().lower(),
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
