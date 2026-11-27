from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Notification, PriceSnapshot, Product, Retailer, Watch
from app.services.alerts import evaluate_watches
from app.services.auth import create_user


@pytest.fixture
def product(db_session, seed_retailers):
    retailer = db_session.scalar(select(Retailer).limit(1))
    p = Product(retailer=retailer, url="http://x.mock/1", title="Widget", current_price=Decimal(1))
    db_session.add(p)
    db_session.flush()
    return p


@pytest.fixture
def make_watch(db_session, product):
    count = [0]

    def _make(**kwargs):
        count[0] += 1
        u = create_user(db_session, f"u{count[0]}@example.com", "pw-pw-pw-pw")
        w = Watch(user_id=u.id, product_id=product.id, **kwargs)
        db_session.add(w)
        db_session.flush()
        return w

    return _make


def snap(db, product, price, in_stock=True):
    s = PriceSnapshot(product_id=product.id, price=Decimal(str(price)), in_stock=in_stock)
    db.add(s)
    db.flush()
    return s


def run(db, product, previous, current):
    ids = evaluate_watches(db, product, previous, current)
    return [db.get(Notification, i) for i in ids]


def test_price_drop_fires_and_sets_flag(db_session, product, make_watch):
    w = make_watch(target_price=Decimal("50"))
    prev, cur = snap(db_session, product, 60), snap(db_session, product, 49.99)
    notes = run(db_session, product, prev, cur)
    assert len(notes) == 1
    n = notes[0]
    assert (n.type, n.price, n.watch_id, n.delivered) == (
        "price_drop",
        Decimal("49.99"),
        w.id,
        False,
    )
    assert n.message == "Price dropped to $49.99 (target $50.00): Widget"
    assert w.price_alert_active is True


def test_no_repeat_then_rearm(db_session, product, make_watch):
    w = make_watch(target_price=Decimal("50"))
    s1, s2, s3, s4, s5 = (snap(db_session, product, p) for p in (40, 39, 55, 45, 44))
    assert len(run(db_session, product, None, s1)) == 1
    assert run(db_session, product, s1, s2) == []
    assert w.price_alert_active is True
    assert run(db_session, product, s2, s3) == []
    assert w.price_alert_active is False
    assert len(run(db_session, product, s3, s4)) == 1
    assert run(db_session, product, s4, s5) == []


def test_new_watch_target_above_current_fires_first_time(db_session, product, make_watch):
    make_watch(target_price=Decimal("100"))
    s1, s2 = snap(db_session, product, 80), snap(db_session, product, 80)
    assert len(run(db_session, product, s1, s2)) == 1


def test_equal_to_target_fires(db_session, product, make_watch):
    make_watch(target_price=Decimal("50"))
    assert len(run(db_session, product, None, snap(db_session, product, 50))) == 1


def test_null_target_never_fires(db_session, product, make_watch):
    make_watch(target_price=None)
    assert run(db_session, product, None, snap(db_session, product, 1)) == []


def test_inactive_watch_ignored(db_session, product, make_watch):
    w = make_watch(target_price=Decimal("50"), notify_on_restock=True, active=False)
    prev, cur = snap(db_session, product, 60, False), snap(db_session, product, 40, True)
    assert run(db_session, product, prev, cur) == []
    assert w.price_alert_active is False


def test_restock_transitions(db_session, product, make_watch):
    make_watch(notify_on_restock=True)
    out, back = snap(db_session, product, 10, False), snap(db_session, product, 10, True)
    notes = run(db_session, product, out, back)
    assert [n.type for n in notes] == ["restock"]
    assert notes[0].message == "Back in stock at $10.00: Widget"
    assert run(db_session, product, back, snap(db_session, product, 10, True)) == []
    assert run(db_session, product, back, snap(db_session, product, 10, False)) == []


def test_restock_requires_flag(db_session, product, make_watch):
    make_watch(notify_on_restock=False)
    out, back = snap(db_session, product, 10, False), snap(db_session, product, 10, True)
    assert run(db_session, product, out, back) == []


def test_first_snapshot_never_restocks(db_session, product, make_watch):
    make_watch(notify_on_restock=True)
    assert run(db_session, product, None, snap(db_session, product, 10, True)) == []


def test_both_fire_same_snapshot(db_session, product, make_watch):
    make_watch(target_price=Decimal("50"), notify_on_restock=True)
    prev, cur = snap(db_session, product, 60, False), snap(db_session, product, 40, True)
    notes = run(db_session, product, prev, cur)
    assert sorted(n.type for n in notes) == ["price_drop", "restock"]


def test_thousands_separator(db_session, product, make_watch):
    make_watch(target_price=Decimal("1500"))
    notes = run(db_session, product, None, snap(db_session, product, 1234.5))
    assert notes[0].message == "Price dropped to $1,234.50 (target $1,500.00): Widget"


def test_multiple_watches_independent(db_session, product, make_watch):
    a, b = make_watch(target_price=Decimal("50")), make_watch(target_price=Decimal("30"))
    notes = run(db_session, product, None, snap(db_session, product, 40))
    assert [n.watch_id for n in notes] == [a.id]
    assert b.price_alert_active is False


def test_does_not_commit(db_session, product, make_watch):
    w = make_watch(target_price=Decimal("50"))
    ids = evaluate_watches(db_session, product, None, snap(db_session, product, 40))
    assert len(ids) == 1
    assert db_session.get(Notification, ids[0]).delivered is False
    assert w.price_alert_active is True
    # nothing was committed: rolling back the outer test transaction state discards it
    db_session.rollback()
    assert db_session.get(Notification, ids[0]) is None
