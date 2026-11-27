import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Retailer, User
from app.seed import seed_admin, seed_retailers
from app.services.auth import verify_password


@pytest.fixture
def admin_env(monkeypatch: pytest.MonkeyPatch):
    def apply(email: str | None, password: str | None) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "ADMIN_EMAIL", email)
        monkeypatch.setattr(settings, "ADMIN_PASSWORD", password)

    return apply


def count_users(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User))


def test_seed_retailers_idempotent(db_session: Session):
    seed_retailers(db_session)
    seed_retailers(db_session)
    assert db_session.scalar(select(func.count()).select_from(Retailer)) == 3


def test_seed_admin_creates_admin(db_session: Session, admin_env):
    admin_env("Root@Example.com", "root-password")
    seed_admin(db_session)
    created = db_session.scalar(select(User).where(User.email == "root@example.com"))
    assert created is not None
    assert created.role == "admin"
    assert verify_password("root-password", created.hashed_password)


def test_seed_admin_idempotent_keeps_password(db_session: Session, admin_env):
    admin_env("root@example.com", "root-password")
    seed_admin(db_session)
    admin_env("root@example.com", "different-password")
    seed_admin(db_session)
    assert count_users(db_session) == 1
    created = db_session.scalar(select(User))
    assert verify_password("root-password", created.hashed_password)


def test_seed_admin_skipped_when_unset(db_session: Session, admin_env):
    admin_env(None, None)
    seed_admin(db_session)
    admin_env("root@example.com", None)
    seed_admin(db_session)
    assert count_users(db_session) == 0
