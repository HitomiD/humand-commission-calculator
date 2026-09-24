"""Tests for the settings read from the environment."""

import pytest

from calculator.config import ConfigError, gemini_api_key, gemini_model, payments_api_url


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


def test_gemini_key_comes_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", " abc ")
    assert gemini_api_key() == "abc"


@pytest.mark.parametrize("value", [None, "", "  "])
def test_missing_gemini_key_is_an_error(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("GEMINI_API_KEY", value)
    with pytest.raises(ConfigError):
        gemini_api_key()


@pytest.mark.parametrize("value", [None, "", "  "])
def test_gemini_model_defaults_to_flash(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("GEMINI_MODEL", raising=False)
    else:
        monkeypatch.setenv("GEMINI_MODEL", value)
    assert gemini_model() == "gemini-2.5-flash"


def test_gemini_model_can_be_overridden(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    assert gemini_model() == "gemini-2.5-pro"
