import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import Settings

DB_VARS = [
    "DATABASE_URL",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_SSLMODE",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in DB_VARS:
        monkeypatch.delenv(name, raising=False)


def load() -> Settings:
    return Settings(_env_file=None)


def test_database_url_takes_precedence(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    monkeypatch.setenv("POSTGRES_HOST", "ignorado")
    assert load().database_url == "postgresql+psycopg://u:p@h:5432/d"


def test_builds_url_from_parts(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "db.ejemplo.com")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("POSTGRES_USER", "polla")
    monkeypatch.setenv("POSTGRES_PASSWORD", "clave")
    monkeypatch.setenv("POSTGRES_DB", "mipolla")
    url = make_url(load().database_url)
    assert url.drivername == "postgresql+psycopg"
    assert (url.host, url.port, url.username, url.password, url.database) == (
        "db.ejemplo.com",
        6543,
        "polla",
        "clave",
        "mipolla",
    )
    assert url.query == {}


def test_special_characters_in_password_survive(monkeypatch):
    password = "p@ss:w/ord#1%?&"
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", password)
    monkeypatch.setenv("POSTGRES_DB", "d")
    url = load().database_url
    assert password not in url  # quedó codificada
    assert make_url(url).password == password
    assert make_url(url).host == "h"


def test_sslmode_added_when_set(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_SSLMODE", "require")
    assert make_url(load().database_url).query == {"sslmode": "require"}


def test_missing_config_fails_fast_and_names_variables(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "h")
    with pytest.raises(ValidationError) as exc:
        load()
    message = str(exc.value)
    assert "POSTGRES_USER" in message
    assert "POSTGRES_PASSWORD" in message
    assert "POSTGRES_DB" in message
    assert "POSTGRES_HOST" not in message.split("estas variables:")[1]


def test_no_hardcoded_credentials_when_nothing_set():
    with pytest.raises(ValidationError):
        load()


def test_empty_env_vars_are_treated_as_unset(monkeypatch):
    # docker-compose pasa "" para las variables sin definir
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_SSLMODE", "")
    monkeypatch.setenv("API_FOOTBALL_SEASON", "")
    s = load()
    assert make_url(s.database_url).host == "h"
    assert make_url(s.database_url).query == {}
    assert s.api_football_season is None
