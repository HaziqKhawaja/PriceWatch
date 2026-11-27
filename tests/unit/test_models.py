from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import PriceSnapshot, Product, Retailer, User, Watch


def _make_graph(db: Session) -> tuple[User, Product]:
    retailer = Retailer(name="ShopAlpha", domain="shopalpha.mock", scraper_key="shopalpha")
    user = User(email="a@example.com", hashed_password="x")
    db.add_all([retailer, user])
    db.flush()
    product = Product(
        retailer_id=retailer.id, url="http://shopalpha.mock:8080/items/1", title="Widget"
    )
    db.add(product)
    db.flush()
    db.add(PriceSnapshot(product_id=product.id, price=Decimal("9.99"), in_stock=True))
    db.flush()
    return user, product


def test_insert_graph_and_defaults(db_session: Session) -> None:
    user, product = _make_graph(db_session)
    db_session.add(Watch(user_id=user.id, product_id=product.id))
    db_session.flush()
    db_session.refresh(user)
    db_session.refresh(product)

    assert user.role == "user"
    assert user.created_at is not None
    assert product.snapshots[0].price == Decimal("9.99")
    assert user.watches[0].active is True
    assert user.watches[0].notify_on_restock is False


def test_watch_unique_user_product(db_session: Session) -> None:
    user, product = _make_graph(db_session)
    db_session.add(Watch(user_id=user.id, product_id=product.id))
    db_session.flush()

    db_session.add(Watch(user_id=user.id, product_id=product.id))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_user_role_check(db_session: Session) -> None:
    db_session.add(User(email="b@example.com", hashed_password="x", role="root"))
    with pytest.raises(IntegrityError):
        db_session.flush()
