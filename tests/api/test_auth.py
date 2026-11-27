from datetime import timedelta

from fastapi.testclient import TestClient

from app.models import User
from app.services.auth import create_access_token

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
PING = "/api/v1/admin/ping"


def test_register_success(client: TestClient):
    resp = client.post(REGISTER, json={"email": "New@Example.com", "password": "password123"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new@example.com"
    assert body["role"] == "user"
    assert "id" in body and "created_at" in body
    assert "password" not in body and "hashed_password" not in body


def test_register_ignores_role_escalation(client: TestClient):
    resp = client.post(
        REGISTER, json={"email": "x@example.com", "password": "password123", "role": "admin"}
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "user"


def test_register_duplicate_case_insensitive(client: TestClient):
    payload = {"email": "dup@example.com", "password": "password123"}
    assert client.post(REGISTER, json=payload).status_code == 201
    resp = client.post(REGISTER, json={**payload, "email": "DUP@example.com"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Email already registered"


def test_register_short_password(client: TestClient):
    resp = client.post(REGISTER, json={"email": "s@example.com", "password": "short"})
    assert resp.status_code == 422


def test_register_invalid_email(client: TestClient):
    resp = client.post(REGISTER, json={"email": "nope", "password": "password123"})
    assert resp.status_code == 422


def test_login_success(client: TestClient, user: User):
    resp = client.post(LOGIN, data={"username": "user@example.com", "password": "user-password"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password(client: TestClient, user: User):
    resp = client.post(LOGIN, data={"username": "user@example.com", "password": "wrong-password"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Incorrect email or password"


def test_login_unknown_email(client: TestClient):
    resp = client.post(LOGIN, data={"username": "ghost@example.com", "password": "whatever123"})
    assert resp.status_code == 401


def test_me_with_token(client: TestClient, user: User, auth_headers: dict[str, str]):
    resp = client.get(ME, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == user.email


def test_me_without_token(client: TestClient):
    resp = client.get(ME)
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


def test_me_with_garbage_token(client: TestClient):
    resp = client.get(ME, headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


def test_me_with_expired_token(client: TestClient, user: User):
    token = create_access_token(user, expires_delta=timedelta(minutes=-5))
    resp = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_me_with_token_for_deleted_user(client: TestClient, db_session, user: User):
    token = create_access_token(user)
    db_session.delete(user)
    db_session.commit()
    resp = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_admin_ping_forbidden_for_user(client: TestClient, auth_headers: dict[str, str]):
    resp = client.get(PING, headers=auth_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin privileges required"


def test_admin_ping_unauthenticated(client: TestClient):
    assert client.get(PING).status_code == 401


def test_admin_ping_ok_for_admin(client: TestClient, admin_headers: dict[str, str]):
    resp = client.get(PING, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
