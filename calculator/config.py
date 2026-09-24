"""Settings read from environment variables.

Read on each call, not at import time, so tests and a running server pick up
changes without reloading the module.
"""

import os

# Default matches the local mock server (mock-api/dev-server.cjs).
DEFAULT_MOCK_BASE_URL = "http://localhost:4000"
PAYMENTS_PATH = "/api/stripe/payments"


def mock_base_url() -> str:
    """Base URL of the payment mock, without a trailing slash."""
    return os.environ.get("MOCK_BASE_URL", DEFAULT_MOCK_BASE_URL).rstrip("/")
