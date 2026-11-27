from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import get_settings
from app.models import User
from app.services.auth import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def make_user() -> User:
    return User(id=42, email="a@example.com", hashed_password="x", role="admin")


def test_hash_and_verify_password():
    hashed = hash_password("s3cret-pass")
    assert hashed != "s3cret-pass"
    assert verify_password("s3cret-pass", hashed)
    assert not verify_password("wrong", hashed)


def test_token_round_trip():
    claims = decode_access_token(create_access_token(make_user()))
    assert claims["sub"] == "42"
    assert claims["role"] == "admin"
    assert "exp" in claims


def test_expired_token_rejected():
    token = create_access_token(make_user(), expires_delta=timedelta(minutes=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token_rejected():
    header, payload, sig = create_access_token(make_user()).split(".")
    forged = jwt.encode(
        {"sub": "1", "role": "admin", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "other",
        algorithm=ALGORITHM,
    ).split(".")[1]
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(f"{header}.{forged}.{sig}")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(f"{header}.{payload}.{sig[:-2]}xx")


def test_wrong_secret_rejected():
    token = jwt.encode(
        {"sub": "1", "role": "user", "exp": datetime.now(UTC) + timedelta(hours=1)},
        get_settings().JWT_SECRET + "-nope",
        algorithm=ALGORITHM,
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token)
