"""Tests for custom_components.remootio.diagnostics."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from custom_components.remootio.const import DOMAIN
from custom_components.remootio.diagnostics import (
    REDACTED,
    async_get_config_entry_diagnostics,
)
from tests.conftest import TEST_AUTH_KEY, TEST_HOST, TEST_SECRET_KEY


def _make_coordinator():
    """Build a mock coordinator for diagnostics tests."""
    coordinator = MagicMock()
    coordinator._device_name = "Test Garage"
    coordinator.api.host = TEST_HOST
    coordinator.data = {1: "open", 2: "closed"}
    coordinator.update_interval = timedelta(seconds=30)
    coordinator.last_update_success = True
    return coordinator


class TestDiagnostics:

    @pytest.mark.asyncio
    async def test_diagnostics_redacts_keys(self):
        """Sensitive API keys must be redacted."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {
            "host": TEST_HOST,
            "api_secret_key": TEST_SECRET_KEY,
            "api_auth_key": TEST_AUTH_KEY,
            "name": "Test Garage",
        }
        hass.data = {DOMAIN: {entry.entry_id: _make_coordinator()}}

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["entry_data"]["api_secret_key"] == REDACTED
        assert result["entry_data"]["api_auth_key"] == REDACTED
        assert result["entry_data"]["host"] == TEST_HOST

    @pytest.mark.asyncio
    async def test_diagnostics_includes_relay_states(self):
        """Diagnostics must include current relay states."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {"host": TEST_HOST}
        hass.data = {DOMAIN: {entry.entry_id: _make_coordinator()}}

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["relay_states"] == {1: "open", 2: "closed"}
        assert result["host"] == TEST_HOST
        assert result["device_name"] == "Test Garage"
        assert result["update_interval_seconds"] == 30.0
        assert result["last_update_success"] is True
