"""Settings read from environment variables.

Read on each call, not at import time, so tests and a running server pick up
changes without reloading the module.
"""

import os


class ConfigError(Exception):
    """A required setting is missing."""


def payments_api_url() -> str:
    """Full URL of the payments endpoint, e.g. ``https://host/api/stripe/payments``.

    Required, with no default: the payments API is treated as an external
    service, so where it lives is always an explicit choice (D-28).
    """
    url = os.environ.get("PAYMENTS_API_URL", "").strip()
    if not url:
        raise ConfigError("PAYMENTS_API_URL is not set")
    return url


def gemini_api_key() -> str:
    """API key for Gemini, which parses the rule texts. Required, no default."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ConfigError("GEMINI_API_KEY is not set")
    return key


def gemini_model() -> str:
    """Gemini model id. Defaults to 2.5 Flash, the one checked with our key (D-33)."""
    return os.environ.get("GEMINI_MODEL", "").strip() or "gemini-2.5-flash"
