"""Tests for the settings read from the environment."""

import pytest

from calculator.config import (ConfigError, data_dir, gemini_api_key, gemini_model, gemini_temperature,
                               payments_api_url)


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


@pytest.mark.parametrize("value", [None, "", "  "])
def test_data_dir_defaults_to_the_repo(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("DATA_DIR", raising=False)
    else:
        monkeypatch.setenv("DATA_DIR", value)
    assert data_dir() is None


def test_data_dir_can_be_relative_or_absolute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", "mis_datos")
    assert data_dir() == tmp_path / "mis_datos"
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "otra"))
    assert data_dir() == tmp_path / "otra"


@pytest.mark.parametrize("value", [None, "", "  "])
def test_gemini_temperature_defaults_to_0(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("GEMINI_TEMPERATURE", raising=False)
    else:
        monkeypatch.setenv("GEMINI_TEMPERATURE", value)
    assert gemini_temperature() == 0


@pytest.mark.parametrize("value, expected", [("0.5", 0.5), (" 1 ", 1), ("2", 2)])
def test_gemini_temperature_can_be_overridden(monkeypatch, value, expected):
    monkeypatch.setenv("GEMINI_TEMPERATURE", value)
    assert gemini_temperature() == expected


@pytest.mark.parametrize("value", ["abc", "-0.1", "2.5", "nan", "inf"])
def test_invalid_gemini_temperature_is_an_error(monkeypatch, value):
    monkeypatch.setenv("GEMINI_TEMPERATURE", value)
    with pytest.raises(ConfigError, match="GEMINI_TEMPERATURE"):
        gemini_temperature()
