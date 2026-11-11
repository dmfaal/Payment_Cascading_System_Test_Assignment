from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables or the root .env."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    stripe_api_key: SecretStr

    @field_validator("stripe_api_key")
    @classmethod
    def validate_test_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("sk_test_"):
            raise ValueError("STRIPE_API_KEY must be a Stripe sandbox secret key (sk_test_)")
        return value


@lru_cache
def get_settings() -> Settings:
    """Load and validate settings once, when first requested."""
    return Settings()
