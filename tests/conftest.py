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
