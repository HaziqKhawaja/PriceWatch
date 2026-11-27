from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ScrapeRun

BASE = "/api/v1/admin"
ROUTES = [
    ("get", f"{BASE}/retailers", None),
    ("post", f"{BASE}/retailers", {"name": "X", "domain": "x.mock", "scraper_key": "shopalpha"}),
    ("patch", f"{BASE}/retailers/1", {"active": False}),
    ("post", f"{BASE}/scrape-runs", None),
    ("get", f"{BASE}/scrape-runs", None),
]

NEW = {"name": "NewShop", "domain": "newshop.mock", "scraper_key": "shopalpha"}


@pytest.fixture
def executed(monkeypatch) -> list[int]:
    calls: list[int] = []
    monkeypatch.setattr("app.api.routes.admin.execute_scrape_run", calls.append)
    return calls


@pytest.mark.parametrize(("method", "url", "body"), ROUTES)
def test_requires_auth(client: TestClient, method, url, body):
    assert client.request(method, url, json=body).status_code == 401


@pytest.mark.parametrize(("method", "url", "body"), ROUTES)
def test_requires_admin(client: TestClient, auth_headers, method, url, body):
    resp = client.request(method, url, json=body, headers=auth_headers)
    assert resp.status_code == 403


def test_list_retailers(client: TestClient, admin_headers, seed_retailers):
    resp = client.get(f"{BASE}/retailers", headers=admin_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert [r["scraper_key"] for r in items] == ["shopalpha", "betamart", "gammagoods"]
    assert set(items[0]) == {"id", "name", "domain", "scraper_key", "active", "rate_limit_seconds"}


def test_create_retailer(client: TestClient, admin_headers):
    resp = client.post(
        f"{BASE}/retailers", json={**NEW, "domain": "  NewShop.Mock "}, headers=admin_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["domain"] == "newshop.mock"
    assert body["rate_limit_seconds"] == 1
    assert body["active"] is True


def test_create_retailer_duplicate(client: TestClient, admin_headers):
    assert client.post(f"{BASE}/retailers", json=NEW, headers=admin_headers).status_code == 201
    resp = client.post(f"{BASE}/retailers", json=NEW, headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Retailer domain already exists"


@pytest.mark.parametrize(
    "override",
    [
        {"scraper_key": "nope"},
        {"domain": "https://newshop.mock"},
        {"domain": "newshop.mock:8080"},
        {"domain": "newshop.mock/path"},
        {"rate_limit_seconds": -1},
    ],
)
def test_create_retailer_invalid(client: TestClient, admin_headers, override):
    resp = client.post(f"{BASE}/retailers", json={**NEW, **override}, headers=admin_headers)
    assert resp.status_code == 422


def test_unknown_scraper_key_message(client: TestClient, admin_headers):
    resp = client.post(
        f"{BASE}/retailers", json={**NEW, "scraper_key": "nope"}, headers=admin_headers
    )
    assert "Unknown scraper_key" in str(resp.json()["detail"])


def test_patch_retailer(client: TestClient, admin_headers, seed_retailers):
    rid = client.get(f"{BASE}/retailers", headers=admin_headers).json()[0]["id"]
    resp = client.patch(
        f"{BASE}/retailers/{rid}",
        json={"active": False, "rate_limit_seconds": 5, "domain": "ignored.mock"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"] is False
    assert body["rate_limit_seconds"] == 5
    assert body["domain"] == "shopalpha.mock"
    assert body["name"] == "ShopAlpha"


def test_patch_retailer_not_found(client: TestClient, admin_headers):
    resp = client.patch(f"{BASE}/retailers/999999", json={"active": False}, headers=admin_headers)
    assert resp.status_code == 404


def test_patch_retailer_invalid_scraper_key(client: TestClient, admin_headers, seed_retailers):
    rid = client.get(f"{BASE}/retailers", headers=admin_headers).json()[0]["id"]
    resp = client.patch(
        f"{BASE}/retailers/{rid}", json={"scraper_key": "nope"}, headers=admin_headers
    )
    assert resp.status_code == 422


def test_trigger_scrape_run(client: TestClient, admin_headers, executed):
    resp = client.post(f"{BASE}/scrape-runs", headers=admin_headers)
    assert resp.status_code == 202
    body = resp.json()
    assert body["finished_at"] is None
    assert executed == [body["id"]]


def test_trigger_scrape_run_conflict(client: TestClient, admin_headers, db_session, executed):
    db_session.add(ScrapeRun(started_at=datetime.now(UTC) - timedelta(minutes=5)))
    db_session.commit()
    resp = client.post(f"{BASE}/scrape-runs", headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "A scrape run is already in progress"
    assert executed == []


def test_list_scrape_runs(client: TestClient, admin_headers, db_session: Session):
    now = datetime.now(UTC)
    for i in range(3):
        db_session.add(
            ScrapeRun(started_at=now - timedelta(hours=3 - i), finished_at=now, succeeded=i)
        )
    db_session.commit()
    resp = client.get(f"{BASE}/scrape-runs?limit=2", headers=admin_headers)
    body = resp.json()
    assert body["total"] == 3
    assert [r["succeeded"] for r in body["items"]] == [2, 1]
    page2 = client.get(f"{BASE}/scrape-runs?limit=2&offset=2", headers=admin_headers).json()
    assert [r["succeeded"] for r in page2["items"]] == [0]


def test_create_retailer_race_integrity_error_returns_409(
    client: TestClient, admin_headers, seed_retailers, db_session, monkeypatch
):
    # Pre-check select misses (concurrent insert); the unique constraint still fires.
    monkeypatch.setattr(db_session, "scalar", lambda *args, **kwargs: None)
    body = {"name": "Dup", "domain": "shopalpha.mock", "scraper_key": "shopalpha"}
    resp = client.post(f"{BASE}/retailers", json=body, headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Retailer domain already exists"
