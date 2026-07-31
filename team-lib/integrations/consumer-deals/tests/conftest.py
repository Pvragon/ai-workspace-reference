"""Isolate every test from the real ~/.config/deals (config, auth, and the new
detail cache all live under DEALS_CONFIG_DIR)."""
import pytest


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DEALS_CONFIG_DIR", str(tmp_path / "deals-cfg"))
    yield
