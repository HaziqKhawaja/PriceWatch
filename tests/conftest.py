import os
from argparse import Namespace
from collections.abc import Iterator
from pathlib import Path

os.environ["SCHEDULER_ENABLED"] = "false"

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import User
from app.services.auth import create_access_token, create_user

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def alembic_config(db_url: str) -> Config:
    config = Config(str(ALEMBIC_INI), cmd_opts=Namespace(x=[f"db_url={db_url}"]))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    return config


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = get_settings().TEST_DATABASE_URL
    command.upgrade(alembic_config(url), "head")
    test_engine = create_engine(url)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def user(db_session: Session) -> User:
    return create_user(db_session, "user@example.com", "user-password")


@pytest.fixture
def admin(db_session: Session) -> User:
    return create_user(db_session, "admin@example.com", "admin-password", role="admin")


@pytest.fixture
def user_token(user: User) -> str:
    return create_access_token(user)


@pytest.fixture
def admin_token(admin: User) -> str:
    return create_access_token(admin)


@pytest.fixture
def auth_headers(user_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}
