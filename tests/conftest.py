"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def _example_data(monkeypatch):
    # ``.env`` is loaded on import; a DATA_DIR set there must not change which
    # files the tests read. Tests that need it set it themselves.
    monkeypatch.delenv("DATA_DIR", raising=False)
