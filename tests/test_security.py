from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings
from app.core.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_salted_and_verifiable():
    h1, h2 = hash_password("secreta123"), hash_password("secreta123")
    assert h1 != h2
    assert h1 != "secreta123"
    assert verify_password("secreta123", h1)
    assert not verify_password("otra-clave", h1)


def test_verify_password_with_garbage_hash_is_false():
    assert verify_password("x", "no-es-un-hash") is False


def test_token_roundtrip():
    assert decode_access_token(create_access_token(42)) == 42


def test_token_rejected_when_invalid():
    assert decode_access_token("basura") is None
    assert decode_access_token("") is None


def test_token_rejected_with_wrong_key_or_missing_sub():
    wrong_key = jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "otra-clave-distinta-de-32-bytes-o-mas!!",
        ALGORITHM,
    )
    no_sub = jwt.encode(
        {"exp": datetime.now(UTC) + timedelta(hours=1)}, settings.secret_key, ALGORITHM
    )
    not_int = jwt.encode(
        {"sub": "abc", "exp": datetime.now(UTC) + timedelta(hours=1)},
        settings.secret_key,
        ALGORITHM,
    )
    assert decode_access_token(wrong_key) is None
    assert decode_access_token(no_sub) is None
    assert decode_access_token(not_int) is None


def test_token_rejected_when_alg_none():
    forged = jwt.encode({"sub": "1"}, key=None, algorithm="none")
    assert decode_access_token(forged) is None
