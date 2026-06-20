"""Tests for custom_components.remootio.__init__."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.remootio import async_setup_entry, async_unload_entry
from custom_components.remootio.const import DOMAIN
from tests.conftest import TEST_AUTH_KEY, TEST_HOST, TEST_SECRET_KEY, make_query_response


CONF_HOST = "host"
CONF_API_SECRET_KEY = "api_secret_key"
CONF_API_AUTH_KEY = "api_auth_key"
CONF_NAME = "name"


def _make_entry(entry_id="test_entry"):
    """Build a mock config entry."""
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {
        CONF_HOST: TEST_HOST,
        CONF_API_SECRET_KEY: TEST_SECRET_KEY,
        CONF_API_AUTH_KEY: TEST_AUTH_KEY,
        CONF_NAME: "Test Garage",
    }
    return entry


class TestAsyncSetupEntry:

    @pytest.mark.asyncio
    async def test_async_setup_entry(self):
        hass = MagicMock()
        hass.data = {}
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        entry = _make_entry()

        mock_coordinator = MagicMock()
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator.async_start_event_listener = AsyncMock()
        mock_coordinator.async_stop_event_listener = AsyncMock()

        with patch("custom_components.remootio.RemootioAPI") as mock_api_cls, \
             patch("custom_components.remootio.RemootioCoordinator", return_value=mock_coordinator):
            result = await async_setup_entry(hass, entry)

        assert result is True
        assert entry.entry_id in hass.data[DOMAIN]
        assert hass.data[DOMAIN][entry.entry_id] is mock_coordinator
        mock_coordinator.async_config_entry_first_refresh.assert_called_once()
        mock_coordinator.async_start_event_listener.assert_awaited_once()
        hass.config_entries.async_forward_entry_setups.assert_called_once()
        # Stop listener must be registered for cleanup on unload
        entry.async_on_unload.assert_called_once_with(mock_coordinator.async_stop_event_listener)


class TestAsyncUnloadEntry:

    @pytest.mark.asyncio
    async def test_async_unload_entry_success(self):
        hass = MagicMock()
        entry = _make_entry()
        hass.data = {DOMAIN: {entry.entry_id: MagicMock()}}
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(hass, entry)

        assert result is True
        assert entry.entry_id not in hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_async_unload_entry_failure(self):
        hass = MagicMock()
        entry = _make_entry()
        coordinator = MagicMock()
        hass.data = {DOMAIN: {entry.entry_id: coordinator}}
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

        result = await async_unload_entry(hass, entry)

        assert result is False
        assert entry.entry_id in hass.data[DOMAIN]
        assert hass.data[DOMAIN][entry.entry_id] is coordinator
