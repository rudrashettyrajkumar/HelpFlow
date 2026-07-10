"""Password hashing + JWT mint/decode (spec E5 Required tests)."""

from datetime import UTC, datetime, timedelta

import pytest
from jose import JWTError

from backend.utils.security import decode_jwt, hash_password, issue_jwt, verify_password


def test_hash_and_verify_roundtrip():
    stored = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", stored) is True


def test_verify_rejects_wrong_password():
    stored = hash_password("correct horse battery staple")
    assert verify_password("wrong password", stored) is False


def test_verify_never_raises_on_malformed_stored_value():
    assert verify_password("anything", "not-a-valid-hash") is False
    assert verify_password("anything", "") is False


def test_two_hashes_of_the_same_password_differ_by_salt():
    a = hash_password("same password")
    b = hash_password("same password")
    assert a != b
    assert verify_password("same password", a)
    assert verify_password("same password", b)


def test_issue_and_decode_roundtrip():
    token = issue_jwt(user_id="user-1")
    claims = decode_jwt(token)
    assert claims["sub"] == "user-1"
    assert set(claims) == {"sub", "exp"}  # spec E5 Req 2: sub + exp only, no PII


def test_decode_rejects_expired_token():
    token = issue_jwt(user_id="user-1", now=datetime.now(UTC) - timedelta(days=30))
    with pytest.raises(JWTError):
        decode_jwt(token)


def test_decode_rejects_bad_signature():
    token = issue_jwt(user_id="user-1")
    with pytest.raises(JWTError):
        decode_jwt(token + "tampered")


def test_issue_jwt_raises_clearly_when_secret_unconfigured(monkeypatch):
    from backend.utils.config import get_settings

    monkeypatch.delenv("JWT_SECRET", raising=False)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        issue_jwt(user_id="user-1")
    get_settings.cache_clear()
