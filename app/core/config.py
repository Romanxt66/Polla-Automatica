from pydantic import model_validator
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

    secret_key: str = "dev-only-secret-key-change-me-in-env-32b"
    access_token_expire_minutes: int = 60
    results_provider: str = "fake"  # fake | api_football
    api_football_key: str = ""
    api_football_season: int | None = None  # vacío = se deduce por competición
    scheduler_enabled: bool = False
    # Orígenes permitidos para el frontend web, separados por coma. Vacío = sin CORS.
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def build_database_url(self) -> "Settings":
        """Si no hay DATABASE_URL, la arma con POSTGRES_*. La contraseña se codifica sola,
        así que puede llevar caracteres como @ : / # sin romper la URL."""
        if self.database_url:
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
