from logging.config import fileConfig

from sqlalchemy import create_engine, text

from alembic import context
from app.core.config import settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(settings.database_url, connect_args=settings.db_connect_args)
    with engine.connect() as connection:
        if settings.db_schema:
            # el esquema se crea antes de migrar; el search_path de la conexión hace que las
            # tablas (y alembic_version) queden dentro de él y no en public
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"'))
            connection.commit()
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
