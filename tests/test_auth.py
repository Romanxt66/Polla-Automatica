from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings
from app.core.security import ALGORITHM

USER = {"email": "Ana@Example.com", "username": "ana", "password": "supersecreta1"}


def register(client, **overrides):
    return client.post("/auth/register", json={**USER, **overrides})


def token_for(client) -> str:
    register(client)
    r = client.post("/auth/login", json={"email": USER["email"], "password": USER["password"]})
    return r.json()["access_token"]


def test_register_ok_and_hides_password(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "ana@example.com"
    assert body["username"] == "ana"
    assert "password" not in body and "hashed_password" not in body


def test_register_duplicate_email_case_insensitive(client):
    register(client)
    r = register(client, email="ANA@example.com", username="otra")
    assert r.status_code == 409


def test_register_duplicate_username(client):
    register(client)
    r = register(client, email="otra@example.com", username="ANA")
    assert r.status_code == 409


def test_register_validation(client):
    assert register(client, password="corta").status_code == 422
    assert register(client, email="no-es-email").status_code == 422
    assert register(client, username="a b").status_code == 422
    assert register(client, password="ñ" * 40).status_code == 422  # >72 bytes


def test_login_ok(client):
    register(client)
    r = client.post("/auth/login", json={"email": "ana@example.com", "password": USER["password"]})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    assert r.json()["access_token"]


def test_login_wrong_password_and_unknown_user(client):
    register(client)
    bad = client.post("/auth/login", json={"email": "ana@example.com", "password": "incorrecta1"})
    unknown = client.post("/auth/login", json={"email": "x@example.com", "password": "loquesea12"})
    assert bad.status_code == 401
    assert unknown.status_code == 401
    assert bad.json() == unknown.json()  # no revela si el email existe


def test_me_with_token(client):
    token = token_for(client)
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "ana"


def test_me_without_or_bad_token(client):
    assert client.get("/auth/me").status_code == 401
    r = client.get("/auth/me", headers={"Authorization": "Bearer basura"})
    assert r.status_code == 401


def test_me_expired_token(client):
    register(client)
    expired = jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.secret_key,
        ALGORITHM,
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_me_token_for_deleted_user(client, db):
    token = token_for(client)
    from app.models import User

    db.delete(db.get(User, 1))
    db.commit()
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
