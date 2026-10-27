
"""Baseten implementation of the methodology provider interface.

Uses Baseten's OpenAI-compatible chat completions API, sharing the
extraction prompts and response handling with the Fireworks adapter.
"""

from bizora.providers.base import MethodologyProviderError
from bizora.providers.fireworks import FireworksMethodologyProvider


class BasetenProviderError(MethodologyProviderError):
    """Raised when Baseten cannot return a usable methodology draft."""


class BasetenMethodologyProvider(FireworksMethodologyProvider):
    """Extract drafts using Baseten chat completions (e.g. Muse Spark)."""

    DEFAULT_BASE_URL = "https://inference.baseten.co/v1"

    provider_name = "baseten"
    error_label = "Baseten"
    error_type: type[MethodologyProviderError] = BasetenProviderError
