from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://pricewatch:pricewatch@db:5432/pricewatch"
    TEST_DATABASE_URL: str = (
        "postgresql+psycopg://pricewatch:pricewatch@db-test:5432/pricewatch_test"
    )
    # Insecure development default; must be overridden outside local dev.
    JWT_SECRET: str = "dev-insecure-secret"
    JWT_EXPIRE_MINUTES: int = 60
    SCRAPE_INTERVAL_MINUTES: int = 60
    SCHEDULER_ENABLED: bool = True
    SCRAPER_TIMEOUT_SECONDS: int = 10
    SCRAPER_MAX_RETRIES: int = 3
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD: str | None = None
    LOG_LEVEL: str = "INFO"
    # Comma-separated hostnames exempt from the webhook private-address block
    # (e.g. "host.docker.internal" for local testing). Empty = no exemptions.
    WEBHOOK_ALLOWED_HOSTS: str = ""

    @property
    def webhook_allowed_hosts(self) -> frozenset[str]:
        hosts = (h.strip().lower().rstrip(".") for h in self.WEBHOOK_ALLOWED_HOSTS.split(","))
        return frozenset(h for h in hosts if h)


@lru_cache
def get_settings() -> Settings:
    return Settings()
