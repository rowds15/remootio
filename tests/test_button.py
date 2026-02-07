"""Tests for custom_components.remootio.button."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.remootio.button import RemootioButton
from tests.conftest import TEST_HOST


def _make_coordinator():
    """Build a minimal mock coordinator for button tests."""
    coordinator = MagicMock()
    coordinator.host = TEST_HOST
    coordinator.device_info = {"identifiers": {("remootio", TEST_HOST)}}
    coordinator.async_trigger = AsyncMock()
    return coordinator


class TestButtonPress:

    @pytest.mark.asyncio
    async def test_async_press_triggers_relay_1(self):
        coordinator = _make_coordinator()
        button = RemootioButton(coordinator, 1)
        await button.async_press()
        coordinator.async_trigger.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_async_press_triggers_relay_2(self):
        coordinator = _make_coordinator()
        button = RemootioButton(coordinator, 2)
        await button.async_press()
        coordinator.async_trigger.assert_called_once_with(2)


class TestButtonMetadata:

    def test_unique_ids(self):
        coordinator = _make_coordinator()
        host_safe = TEST_HOST.replace(".", "_")
        button1 = RemootioButton(coordinator, 1)
        button2 = RemootioButton(coordinator, 2)
        assert button1._attr_unique_id == f"remootio_{host_safe}_toggle_ch1"
        assert button2._attr_unique_id == f"remootio_{host_safe}_toggle_ch2"

    def test_device_info_delegates(self):
        coordinator = _make_coordinator()
        button = RemootioButton(coordinator, 1)
        assert button.device_info is coordinator.device_info

    def test_icon(self):
        coordinator = _make_coordinator()
        button = RemootioButton(coordinator, 1)
        assert button._attr_icon == "mdi:garage"
