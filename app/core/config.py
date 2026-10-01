import re

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    # Base de datos: o bien DATABASE_URL completa, o bien las piezas POSTGRES_*.
    # Sin valores por defecto: las credenciales salen siempre del entorno / .env.
    database_url: str = ""
    postgres_host: str = ""
    postgres_port: int = 5432
    postgres_user: str = ""
    postgres_password: str = ""
    postgres_db: str = ""
    postgres_sslmode: str = ""  # ej. "require" para servidores remotos
    # Esquema de Postgres donde viven las tablas (se crea si no existe). Para usar el de
    # siempre pon DATABASE_SCHEMA=public. No aplica a SQLite.
    database_schema: str = "polla_futbolera"

    secret_key: str = "dev-only-secret-key-change-me-in-env-32b"
    access_token_expire_minutes: int = 60
    results_provider: str = "fake"  # fake | api_football | football_data
    api_football_key: str = ""
    football_data_token: str = ""
    football_data_season: int | None = None  # vacío = temporada en curso
    api_football_season: int | None = None  # vacío = se deduce por competición
    scheduler_enabled: bool = False
    # Cada cuántos minutos se consultan resultados de partidos en juego (cuida la cuota)
    settle_interval_minutes: int = Field(default=5, ge=1, le=60)
    # Orígenes permitidos para el frontend web, separados por coma. Vacío = sin CORS.
    cors_origins: str = ""

    @field_validator("database_schema")
    @classmethod
    def schema_is_a_safe_identifier(cls, v: str) -> str:
        if v and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", v):
            raise ValueError("DATABASE_SCHEMA solo admite letras, números y _")
        return v

    @property
    def db_schema(self) -> str:
        """Esquema efectivo: solo se usa con Postgres."""
        is_postgres = self.database_url.startswith("postgresql")
        return self.database_schema if is_postgres else ""

    @property
    def db_connect_args(self) -> dict[str, str]:
        """Fija el search_path de cada conexión al esquema, así las tablas se crean y se
        consultan ahí sin tener que calificar cada nombre."""
        return {"options": f"-csearch_path={self.db_schema}"} if self.db_schema else {}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def build_database_url(self) -> "Settings":
        """Si no hay DATABASE_URL, la arma con POSTGRES_*. La contraseña se codifica sola,
        así que puede llevar caracteres como @ : / # sin romper la URL."""
        if self.database_url:
            # Coolify y otros entregan "postgres://" o "postgresql://"; SQLAlchemy necesita
            # el driver explícito (psycopg 3).
            for prefix in ("postgres://", "postgresql://"):
                if self.database_url.startswith(prefix):
                    self.database_url = "postgresql+psycopg://" + self.database_url[len(prefix):]
            return self
        required = {
            "POSTGRES_HOST": self.postgres_host,
            "POSTGRES_USER": self.postgres_user,
            "POSTGRES_PASSWORD": self.postgres_password,
            "POSTGRES_DB": self.postgres_db,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(
                "Falta configurar la base de datos: define DATABASE_URL o, en su lugar, "
                f"estas variables: {', '.join(missing)}"
            )
        url = URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
            query={"sslmode": self.postgres_sslmode} if self.postgres_sslmode else {},
        )
        self.database_url = url.render_as_string(hide_password=False)
        return self


settings = Settings()
