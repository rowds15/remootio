"""Tests for custom_components.remootio.cover."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.remootio.cover import RemootioCover
from tests.conftest import TEST_HOST


def _make_coordinator(data=None):
    """Build a minimal mock coordinator for cover tests."""
    coordinator = MagicMock()
    coordinator.host = TEST_HOST
    coordinator.data = data or {1: "open", 2: "closed"}
    coordinator.device_info = {"identifiers": {("remootio", TEST_HOST)}}
    coordinator.async_trigger = AsyncMock()
    return coordinator


class TestCoverState:

    def test_is_closed_when_closed(self):
        coordinator = _make_coordinator({1: "closed"})
        cover = RemootioCover(coordinator, 1)
        assert cover.is_closed is True
        assert cover.is_open is False

    def test_is_open_when_open(self):
        coordinator = _make_coordinator({1: "open"})
        cover = RemootioCover(coordinator, 1)
        assert cover.is_closed is False
        assert cover.is_open is True

    def test_is_closed_when_none(self):
        coordinator = _make_coordinator({1: None})
        cover = RemootioCover(coordinator, 1)
        assert cover.is_closed is None
        assert cover.is_open is None


class TestCoverActions:

    @pytest.mark.asyncio
    async def test_async_open_cover(self):
        coordinator = _make_coordinator()
        cover = RemootioCover(coordinator, 1)
        await cover.async_open_cover()
        coordinator.async_trigger.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_async_close_cover(self):
        coordinator = _make_coordinator()
        cover = RemootioCover(coordinator, 2)
        await cover.async_close_cover()
        coordinator.async_trigger.assert_called_once_with(2)


class TestCoverMetadata:

    def test_unique_ids(self):
        coordinator = _make_coordinator()
        host_safe = TEST_HOST.replace(".", "_")
        cover1 = RemootioCover(coordinator, 1)
        cover2 = RemootioCover(coordinator, 2)
        assert cover1._attr_unique_id == f"remootio_{host_safe}_ch1"
        assert cover2._attr_unique_id == f"remootio_{host_safe}_ch2"

    def test_device_info_delegates(self):
        coordinator = _make_coordinator()
        cover = RemootioCover(coordinator, 1)
        assert cover.device_info is coordinator.device_info

    def test_translation_keys(self):
        coordinator = _make_coordinator()
        cover1 = RemootioCover(coordinator, 1)
        cover2 = RemootioCover(coordinator, 2)
        assert cover1._attr_translation_key == "channel_1"
        assert cover2._attr_translation_key == "channel_2"
