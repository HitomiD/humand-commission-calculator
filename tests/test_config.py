"""Tests for the payments API setting."""

import pytest

from calculator.config import ConfigError, payments_api_url


def test_url_comes_from_env(monkeypatch):
    monkeypatch.setenv("PAYMENTS_API_URL", "https://example.com/api/stripe/payments")
    assert payments_api_url() == "https://example.com/api/stripe/payments"


@pytest.mark.parametrize("value", [None, "", "  "])
def test_missing_url_is_an_error(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("PAYMENTS_API_URL", raising=False)
    else:
        monkeypatch.setenv("PAYMENTS_API_URL", value)
    with pytest.raises(ConfigError):
        payments_api_url()
