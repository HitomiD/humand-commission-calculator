"""Settings read from environment variables.

Read on each call, not at import time, so tests and a running server pick up
changes without reloading the module. For local development, a ``.env`` file
in the working directory is loaded once at import; variables already set in
the environment win over it, and on Vercel there is no file to load.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


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


def data_dir() -> Path | None:
    """Folder with the input CSVs (``hubspot_deals.csv`` and
    ``pagos_aprobados.csv``), from ``DATA_DIR``; None means the repo's
    ``data/``. A relative path is taken from the working directory, so
    others can run the tool on their own data locally (D-47).
    """
    value = os.environ.get("DATA_DIR", "").strip()
    return Path(value).expanduser().resolve() if value else None


# Gemini accepts temperatures from 0 to 2.
MAX_TEMPERATURE = 2.0


def gemini_temperature() -> float:
    """Temperature Gemini reads the rules at. Defaults to 0, the most likely
    reading every time (D-48); the page can override it for one run."""
    raw = os.environ.get("GEMINI_TEMPERATURE", "").strip()
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"GEMINI_TEMPERATURE is not a number: {raw!r}") from None
    if not 0 <= value <= MAX_TEMPERATURE:  # also rejects nan
        raise ConfigError(f"GEMINI_TEMPERATURE must be between 0 and {MAX_TEMPERATURE:g}, not {raw}")
    return value
