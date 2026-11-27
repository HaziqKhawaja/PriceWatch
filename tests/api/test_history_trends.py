import csv
import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models import PriceSnapshot, Product, Retailer

BASE = "/api/v1/products"
SPIKE = 5000.0


def make_product(db, n_days=0, spike_at=None, extra_per_day=0, out_of_stock_day=None):
    retailer = Retailer(
        name="TestShop", domain="testshop.mock", scraper_key="shopalpha", active=True
    )
    db.add(retailer)
    db.flush()
    product = Product(retailer_id=retailer.id, url="http://testshop.mock/items/1", title="Thing")
    db.add(product)
    db.flush()
    now = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    for i in range(n_days):
        when = now - timedelta(days=n_days - 1 - i)
        price = Decimal(50 + i % 5)
        if spike_at == i:
            price = Decimal(SPIKE)
        for k in range(1 + extra_per_day):
            db.add(
                PriceSnapshot(
                    product_id=product.id,
                    price=price,
                    in_stock=out_of_stock_day != i,
                    scraped_at=when + timedelta(minutes=k),
                )
            )
    db.flush()
    return product


@pytest.fixture
def product(db_session):
    return make_product(db_session, n_days=40)


@pytest.mark.parametrize("suffix", ["history", "trends", "history.csv"])
def test_requires_auth(client, product, suffix):
    assert client.get(f"{BASE}/{product.id}/{suffix}").status_code == 401


@pytest.mark.parametrize("suffix", ["history", "trends", "history.csv"])
def test_unknown_product_404(client, auth_headers, suffix):
    resp = client.get(f"{BASE}/999999/{suffix}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Product not found"


def test_history_newest_first_and_pagination(client, auth_headers, product):
    resp = client.get(f"{BASE}/{product.id}/history?limit=10&offset=0", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 40
    assert body["limit"] == 10
    assert len(body["items"]) == 10
    stamps = [i["scraped_at"] for i in body["items"]]
    assert stamps == sorted(stamps, reverse=True)
    assert isinstance(body["items"][0]["price"], str)
    assert set(body["items"][0]) == {"scraped_at", "price", "in_stock"}
    page2 = client.get(f"{BASE}/{product.id}/history?limit=10&offset=35", headers=auth_headers)
    assert len(page2.json()["items"]) == 5
    assert page2.json()["items"][-1]["scraped_at"] < stamps[-1]


def test_trends_shape(client, auth_headers, product):
    resp = client.get(f"{BASE}/{product.id}/trends", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["product_id"] == product.id
    assert body["days"] == 90
    assert body["include_outliers"] is False
    series = body["series"]
    assert len(series) == 40
    dates = [p["date"] for p in series]
    assert dates == sorted(dates)
    for d in dates:
        assert datetime.strptime(d, "%Y-%m-%d")
    for p in series:
        assert set(p) == {"date", "price", "ma_7", "ma_30", "in_stock"}
        assert all(isinstance(p[k], float | int) for k in ("price", "ma_7", "ma_30"))
    stats = body["stats"]
    assert set(stats) == {
        "current",
        "min",
        "max",
        "mean",
        "pct_change",
        "is_all_time_low",
        "vs_30d_avg_pct",
    }
    for k in ("current", "min", "max", "mean", "pct_change", "vs_30d_avg_pct"):
        assert isinstance(stats[k], int | float) and not isinstance(stats[k], bool)
    assert isinstance(stats["is_all_time_low"], bool)
    assert stats["min"] == 50.0
    assert stats["max"] == 54.0


def test_trends_days_narrows(client, auth_headers, product):
    resp = client.get(f"{BASE}/{product.id}/trends?days=10", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["series"]) == 10
    assert resp.json()["days"] == 10


@pytest.mark.parametrize("days", [0, 4000])
def test_trends_days_validation(client, auth_headers, product, days):
    assert (
        client.get(f"{BASE}/{product.id}/trends?days={days}", headers=auth_headers).status_code
        == 422
    )


def test_trends_outliers(client, auth_headers, db_session):
    p = make_product(db_session, n_days=30, spike_at=15)
    default = client.get(f"{BASE}/{p.id}/trends", headers=auth_headers).json()
    included = client.get(
        f"{BASE}/{p.id}/trends?include_outliers=true", headers=auth_headers
    ).json()
    assert default["stats"]["max"] < 100
    assert included["stats"]["max"] == SPIKE
    assert included["include_outliers"] is True


def test_trends_multiple_per_day_and_out_of_stock(client, auth_headers, db_session):
    p = make_product(db_session, n_days=12, extra_per_day=2, out_of_stock_day=11)
    series = client.get(f"{BASE}/{p.id}/trends", headers=auth_headers).json()["series"]
    assert len(series) == 12
    assert series[-1]["in_stock"] is False
    assert series[0]["in_stock"] is True


def test_trends_empty(client, auth_headers, db_session):
    p = make_product(db_session, n_days=0)
    body = client.get(f"{BASE}/{p.id}/trends", headers=auth_headers).json()
    assert body["series"] == []
    assert all(v is None for v in body["stats"].values())


def parse_csv(resp):
    return list(csv.reader(io.StringIO(resp.text)))


def test_raw_csv(client, auth_headers, product):
    resp = client.get(f"{BASE}/{product.id}/history.csv", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/csv; charset=utf-8"
    assert (
        resp.headers["content-disposition"]
        == f'attachment; filename="product-{product.id}-history.csv"'
    )
    rows = parse_csv(resp)
    assert rows[0] == ["scraped_at", "price", "in_stock"]
    assert len(rows) == 41
    ts = datetime.fromisoformat(rows[1][0])
    assert ts.utcoffset() == timedelta(0)
    assert rows[1][1] == "50.00"
    assert rows[1][2] == "True"
    assert [r[0] for r in rows[1:]] == sorted(r[0] for r in rows[1:])


def test_raw_csv_days_filter(client, auth_headers, product):
    resp = client.get(f"{BASE}/{product.id}/history.csv?days=10", headers=auth_headers)
    rows = parse_csv(resp)
    assert rows[0] == ["scraped_at", "price", "in_stock"]
    assert 10 <= len(rows) - 1 <= 11


def test_normalized_csv(client, auth_headers, product):
    resp = client.get(f"{BASE}/{product.id}/history.csv?normalized=true", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/csv; charset=utf-8"
    assert (
        resp.headers["content-disposition"]
        == f'attachment; filename="product-{product.id}-history-normalized.csv"'
    )
    rows = parse_csv(resp)
    assert rows[0] == ["date", "price", "ma_7", "ma_30", "in_stock"]
    assert len(rows) == 41
    narrowed = client.get(
        f"{BASE}/{product.id}/history.csv?normalized=true&days=5", headers=auth_headers
    )
    assert len(parse_csv(narrowed)) == 6


def test_csv_route_not_shadowed(client, auth_headers, product):
    assert client.get(f"{BASE}/{product.id}/history", headers=auth_headers).json()["total"] == 40
    csv_resp = client.get(f"{BASE}/{product.id}/history.csv", headers=auth_headers)
    assert csv_resp.headers["content-type"].startswith("text/csv")
