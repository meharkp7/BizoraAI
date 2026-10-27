
"""Centralized, validated configuration for Bizora.

Database target resolution (canonical source: Settings.database_url):
1. BIZORA_DATABASE_URL from any supported source (init argument, process
   environment, or .env file) wins.
2. Otherwise the legacy DATABASE_URL process-environment override applies.
3. Otherwise the built-in default is used.

Both the application engine and Alembic resolve through this class, so they
always agree on the migration target. When both variables disagree,
BIZORA_DATABASE_URL wins and a warning is emitted. Blank values are never
used as a target; invalid URLs fail fast with an actionable error that
never echoes credentials.
"""

import os
import warnings
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError

DEFAULT_DATABASE_URL = "postgresql+psycopg://bizora:bizora@localhost:5432/bizora"


def is_valid_database_url(value: str) -> bool:
    """Return whether a value parses as a SQLAlchemy database URL."""
    try:
        make_url(value)
    except SQLAlchemyError:
        return False
    return True


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
        hide_input_in_errors=True,
    )

    app_name: str = Field(default="Bizora", alias="BIZORA_APP_NAME")
    environment: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        alias="BIZORA_ENVIRONMENT",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        alias="BIZORA_LOG_LEVEL",
    )
    api_prefix: str = Field(default="/api/v1", alias="BIZORA_API_PREFIX")

    secret_key: SecretStr = Field(
        default=SecretStr(""),
        alias="BIZORA_SECRET_KEY",
    )

    database_url: str = Field(
        default=DEFAULT_DATABASE_URL,
        alias="BIZORA_DATABASE_URL",
    )

    meta_api_key: SecretStr | None = Field(default=None, alias="META_API_KEY")
    muse_model_api_base_url: str | None = Field(
        default=None,
        alias="MUSE_MODEL_API_BASE_URL",
    )
    muse_model_name: str | None = Field(default=None, alias="MUSE_MODEL_NAME")

    fireworks_api_key: SecretStr | None = Field(
        default=None,
        alias="FIREWORKS_API_KEY",
    )
    fireworks_base_url: str = Field(
        default="https://api.fireworks.ai/inference/v1",
        alias="FIREWORKS_BASE_URL",
    )
    fireworks_model_name: str | None = Field(
        default=None,
        alias="FIREWORKS_MODEL_NAME",
    )

    baseten_api_key: SecretStr | None = Field(default=None, alias="BASETEN_API_KEY")
    baseten_model_url: str | None = Field(default=None, alias="BASETEN_MODEL_URL")
    baseten_base_url: str = Field(
        default="https://inference.baseten.co/v1",
        alias="BASETEN_BASE_URL",
    )
    baseten_model_name: str | None = Field(
        default=None,
        alias="BASETEN_MODEL_NAME",
    )

    modal_token_id: SecretStr | None = Field(default=None, alias="MODAL_TOKEN_ID")
    modal_token_secret: SecretStr | None = Field(
        default=None,
        alias="MODAL_TOKEN_SECRET",
    )
    modal_app_name: str = Field(
        default="bizora-experiments",
        alias="MODAL_APP_NAME",
    )

    max_upload_mb: int = Field(
        default=50,
        ge=1,
        le=500,
        alias="BIZORA_MAX_UPLOAD_MB",
    )
    max_experiment_minutes: int = Field(
        default=60,
        ge=1,
        le=1440,
        alias="BIZORA_MAX_EXPERIMENT_MINUTES",
    )
    max_concurrent_experiments: int = Field(
        default=2,
        ge=1,
        le=32,
        alias="BIZORA_MAX_CONCURRENT_EXPERIMENTS",
    )

    enable_fireworks: bool = Field(default=False, alias="BIZORA_ENABLE_FIREWORKS")
    enable_baseten: bool = Field(default=False, alias="BIZORA_ENABLE_BASETEN")
    enable_modal: bool = Field(default=False, alias="BIZORA_ENABLE_MODAL")

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        """Require an absolute API path without a trailing slash."""
        normalized = value.strip()
        if not normalized.startswith("/") or normalized == "/":
            raise ValueError("API prefix must start with '/' and cannot be '/' alone.")
        if normalized.endswith("/"):
            normalized = normalized.rstrip("/")
        return normalized

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Reject blank or unparseable primary database URLs."""
        if not value.strip():
            raise ValueError("BIZORA_DATABASE_URL must not be empty.")
        if not is_valid_database_url(value):
            raise ValueError("BIZORA_DATABASE_URL must be a valid SQLAlchemy database URL.")
        return value

    @model_validator(mode="after")
    def apply_legacy_database_url(self) -> "Settings":
        """Apply DATABASE_URL only when BIZORA_DATABASE_URL is unset.

        An explicitly configured primary URL always wins; a disagreeing
        legacy override is ignored with a warning instead of silently
        redirecting migrations away from the application target.
        """
        legacy = os.environ.get("DATABASE_URL", "").strip()
        if not legacy:
            return self
        if self.database_url != DEFAULT_DATABASE_URL:
            if legacy != self.database_url:
                warnings.warn(
                    "Both BIZORA_DATABASE_URL and DATABASE_URL are set; using BIZORA_DATABASE_URL.",
                    stacklevel=2,
                )
            return self
        if not is_valid_database_url(legacy):
            raise ValueError("DATABASE_URL must be a valid SQLAlchemy database URL.")
        self.database_url = legacy
        return self

    @field_validator("secret_key")
    @classmethod
    def reject_placeholder_secret(cls, value: SecretStr, info: object) -> SecretStr:
        """Reject the documented placeholder when an actual key is supplied."""
        raw = value.get_secret_value()
        if raw and raw == "replace-with-a-random-secret-before-running":
            raise ValueError("Replace the example secret with a generated secret.")
        return value

    def validate_provider_configuration(self) -> None:
        """Ensure enabled integrations have their required credentials."""
        if self.enable_fireworks and not self.fireworks_api_key:
            raise ValueError("Fireworks is enabled but FIREWORKS_API_KEY is missing.")

        if self.enable_baseten and not (
            self.baseten_api_key
            and (self.baseten_model_url or self.baseten_model_name)
        ):
            raise ValueError(
                "Baseten is enabled but its API key, model URL, "
                "or model name is missing."
            )

        if self.enable_modal and not (
            self.modal_token_id and self.modal_token_secret
        ):
            raise ValueError(
                "Modal is enabled but its token ID or token secret is missing."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance for the current process."""
    settings = Settings()
    settings.validate_provider_configuration()
    return settings
