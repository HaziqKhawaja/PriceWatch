from sqlalchemy.orm import Session

from app.db import get_db


def test_get_db_yields_and_closes_session():
    gen = get_db()
    db = next(gen)
    assert isinstance(db, Session)
    gen.close()
