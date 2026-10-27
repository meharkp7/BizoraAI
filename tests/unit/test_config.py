
"""Tests for Bizora's centralized application settings."""

import pytest
from pydantic import ValidationError

from bizora.core.config import Settings


def test_default_settings_are_safe_for_local_development() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "Bizora"
    assert settings.environment == "development"
    assert settings.api_prefix == "/api/v1"
    assert settings.enable_fireworks is False
    assert settings.enable_baseten is False
    assert settings.enable_modal is False


def test_api_prefix_removes_trailing_slash() -> None:
    settings = Settings(_env_file=None, BIZORA_API_PREFIX="/api/v1/")

    assert settings.api_prefix == "/api/v1"


def test_api_prefix_rejects_root_path() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, BIZORA_API_PREFIX="/")


def test_upload_limit_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, BIZORA_MAX_UPLOAD_MB=0)


def test_experiment_duration_has_an_upper_bound() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, BIZORA_MAX_EXPERIMENT_MINUTES=1441)


def test_fireworks_requires_credentials_when_enabled() -> None:
    settings = Settings(
        _env_file=None,
        BIZORA_ENABLE_FIREWORKS=True,
    )

    with pytest.raises(ValueError, match="FIREWORKS_API_KEY"):
        settings.validate_provider_configuration()


def test_baseten_requires_key_and_model_url_when_enabled() -> None:
    settings = Settings(
        _env_file=None,
        BIZORA_ENABLE_BASETEN=True,
        BASETEN_API_KEY="test-key",
    )

    with pytest.raises(ValueError, match="model URL"):
        settings.validate_provider_configuration()


def test_modal_requires_both_token_values_when_enabled() -> None:
    settings = Settings(
        _env_file=None,
        BIZORA_ENABLE_MODAL=True,
        MODAL_TOKEN_ID="test-id",
    )

    with pytest.raises(ValueError, match="token ID or token secret"):
        settings.validate_provider_configuration()


def test_baseten_accepts_model_name_without_model_url() -> None:
    settings = Settings(
        _env_file=None,
        BIZORA_ENABLE_BASETEN=True,
        BASETEN_API_KEY="test-key",
        BASETEN_MODEL_NAME="meta-models/muse-spark-open-1026",
    )

    settings.validate_provider_configuration()

    assert settings.baseten_base_url == "https://inference.baseten.co/v1"


def test_baseten_accepts_model_url_without_model_name() -> None:
    settings = Settings(
        _env_file=None,
        BIZORA_ENABLE_BASETEN=True,
        BASETEN_API_KEY="test-key",
        BASETEN_MODEL_URL="https://example.baseten.co/deployment",
    )

    settings.validate_provider_configuration()


def test_configured_provider_passes_validation() -> None:
    settings = Settings(
        _env_file=None,
        BIZORA_ENABLE_FIREWORKS=True,
        FIREWORKS_API_KEY="test-key",
    )

    settings.validate_provider_configuration()
