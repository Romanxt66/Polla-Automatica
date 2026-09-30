"""Verifica contra un Postgres REAL que las tablas quedan en DATABASE_SCHEMA y no en public.

Se omite si no hay Postgres: define TEST_PG_URL (en CI lo hace el job de migraciones).
"""

import os

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.core.config import settings

PG_URL = os.environ.get("TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="TEST_PG_URL no definido")

SCHEMA = "polla_test_schema"
TABLES = {
    "users",
    "competitions",
    "matches",
    "groups",
    "group_members",
    "invites",
    "predictions",
    "points_ledger",
    "alembic_version",
}


@pytest.fixture()
def pg(monkeypatch):
    engine = create_engine(PG_URL)
    with engine.begin() as c:
        c.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    monkeypatch.setattr(settings, "database_url", PG_URL)
    monkeypatch.setattr(settings, "database_schema", SCHEMA)
    yield engine
    with engine.begin() as c:
        c.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    engine.dispose()


def tables_in(engine, schema):
    with engine.connect() as c:
        rows = c.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"),
            {"s": schema},
        )
        return {r[0] for r in rows}


def test_migrations_create_schema_and_put_every_table_in_it(pg):
    command.upgrade(Config("alembic.ini"), "head")
    assert tables_in(pg, SCHEMA) == TABLES
    with pg.connect() as c:
        seeded = {r[0] for r in c.execute(text(f'SELECT code FROM "{SCHEMA}".competitions'))}
    assert seeded == {"BETPLAY", "UCL", "PL"}


def test_public_schema_is_left_untouched(pg):
    before = tables_in(pg, "public")
    command.upgrade(Config("alembic.ini"), "head")
    assert tables_in(pg, "public") == before


def test_upgrade_is_repeatable(pg):
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    assert tables_in(pg, SCHEMA) == TABLES
