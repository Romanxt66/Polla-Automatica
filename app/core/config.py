from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://polla:polla@localhost:5432/polla"
    secret_key: str = "dev-only-secret-key-change-me-in-env-32b"
    access_token_expire_minutes: int = 60
    results_provider: str = "fake"  # fake | api_football
    api_football_key: str = ""
    scheduler_enabled: bool = False


settings = Settings()
