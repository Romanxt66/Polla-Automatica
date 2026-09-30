import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from alembic import command
from app.core.config import settings
from app.models import Base


@pytest.fixture()
def migrated_url(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    monkeypatch.setattr(settings, "database_url", url)  # alembic/env.py lee settings
    command.upgrade(Config("alembic.ini"), "head")
    return url


def test_upgrade_creates_all_tables_and_seeds_competitions(migrated_url):
    engine = create_engine(migrated_url)
    with engine.connect() as conn:
        tables = set(Base.metadata.tables)
        for table in tables:
            conn.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
        codes = {r[0] for r in conn.execute(text("SELECT code FROM competitions"))}
    assert codes == {"BETPLAY", "UCL", "PL"}


def test_migrations_match_models(migrated_url):
    engine = create_engine(migrated_url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"Faltan migraciones para los modelos: {diff}"


def test_downgrade_then_upgrade_is_clean(migrated_url):
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(migrated_url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM competitions")).scalar() == 3
