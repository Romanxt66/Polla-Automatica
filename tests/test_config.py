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


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_database_url_scheme_is_normalized_for_psycopg(monkeypatch, scheme):
    monkeypatch.setenv("DATABASE_URL", f"{scheme}://u:p@host:5432/db?sslmode=require")
    assert load().database_url == "postgresql+psycopg://u:p@host:5432/db?sslmode=require"


def test_explicit_driver_in_url_is_left_alone(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    assert load().database_url == "postgresql+psycopg://u:p@h/db"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///x.db")
    assert load().database_url == "sqlite:///x.db"


def test_schema_defaults_to_polla_futbolera_on_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    s = load()
    assert s.db_schema == "polla_futbolera"
    assert s.db_connect_args == {"options": "-csearch_path=polla_futbolera"}


def test_schema_can_be_changed_or_disabled(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h/db")
    monkeypatch.setenv("DATABASE_SCHEMA", "otro")
    assert load().db_connect_args == {"options": "-csearch_path=otro"}
    monkeypatch.setenv("DATABASE_SCHEMA", "")  # vacío se ignora -> valor por defecto
    assert load().db_schema == "polla_futbolera"


def test_schema_not_applied_to_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///x.db")
    s = load()
    assert s.db_schema == "" and s.db_connect_args == {}


@pytest.mark.parametrize("bad", ["a;drop table x", 'a"b', "1abc", "con espacio", "a-b"])
def test_schema_rejects_unsafe_names(monkeypatch, bad):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("DATABASE_SCHEMA", bad)
    with pytest.raises(ValidationError):
        load()
