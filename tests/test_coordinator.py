"""Tests for custom_components.remootio.coordinator."""
from __future__ import annotations

from unittest.mock import AsyncMock, call, patch

import pytest

from custom_components.remootio.coordinator import RemootioCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed
from tests.conftest import TEST_HOST, make_query_response


class TestAsyncUpdateData:
    """Tests for the coordinator's _async_update_data method."""

    @pytest.mark.asyncio
    async def test_update_both_relays_success(self, mock_coordinator):
        """Both relays return valid states."""
        mock_coordinator.api.async_send_command = AsyncMock(side_effect=[
            make_query_response("open"),
            make_query_response("closed"),
        ])

        result = await mock_coordinator._async_update_data()

        assert result == {1: "open", 2: "closed"}

    @pytest.mark.asyncio
    async def test_update_one_relay_fails(self, mock_coordinator):
        """One relay returns None — falls back to previous state, no UpdateFailed."""
        mock_coordinator._previous_states = {1: "open", 2: "closed"}
        mock_coordinator.api.async_send_command = AsyncMock(side_effect=[
            None,  # relay 1 fails
            make_query_response("open"),  # relay 2 succeeds
        ])

        result = await mock_coordinator._async_update_data()

        assert result[1] == "open"  # fallback to previous
        assert result[2] == "open"

    @pytest.mark.asyncio
    async def test_update_both_relays_fail(self, mock_coordinator):
        """Both relays return None — raises UpdateFailed."""
        mock_coordinator._previous_states = {1: "open", 2: "closed"}
        mock_coordinator.api.async_send_command = AsyncMock(return_value=None)

        with pytest.raises(UpdateFailed):
            await mock_coordinator._async_update_data()


class TestStateTransitionSignals:
    """Tests for dispatcher signal firing on state transitions."""

    @pytest.mark.asyncio
    async def test_state_transition_fires_signal(self, mock_coordinator):
        """Transition from closed→open fires dispatcher signal with (old, new)."""
        mock_coordinator._previous_states = {1: "closed", 2: "closed"}
        mock_coordinator.api.async_send_command = AsyncMock(side_effect=[
            make_query_response("open"),
            make_query_response("closed"),
        ])

        with patch("custom_components.remootio.coordinator.async_dispatcher_send") as mock_send:
            await mock_coordinator._async_update_data()

            mock_send.assert_called_once_with(
                mock_coordinator.hass,
                f"remootio_state_changed_{TEST_HOST}_ch1",
                "closed",
                "open",
            )

    @pytest.mark.asyncio
    async def test_no_signal_on_same_state(self, mock_coordinator):
        """Same state → no dispatcher call."""
        mock_coordinator._previous_states = {1: "open", 2: "closed"}
        mock_coordinator.api.async_send_command = AsyncMock(side_effect=[
            make_query_response("open"),
            make_query_response("closed"),
        ])

        with patch("custom_components.remootio.coordinator.async_dispatcher_send") as mock_send:
            await mock_coordinator._async_update_data()

            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_signal_when_previous_none(self, mock_coordinator):
        """Previous state is None → no dispatcher call (initial poll)."""
        mock_coordinator._previous_states = {1: None, 2: None}
        mock_coordinator.api.async_send_command = AsyncMock(side_effect=[
            make_query_response("open"),
            make_query_response("closed"),
        ])

        with patch("custom_components.remootio.coordinator.async_dispatcher_send") as mock_send:
            await mock_coordinator._async_update_data()

            mock_send.assert_not_called()


class TestAsyncTrigger:
    """Tests for the coordinator's async_trigger method."""

    @pytest.mark.asyncio
    async def test_async_trigger(self, mock_coordinator):
        """async_trigger sends TRIGGER command then requests refresh."""
        mock_coordinator.api.async_send_command = AsyncMock(side_effect=[
            None,  # TRIGGER command response (ignored)
            make_query_response("open"),  # refresh: relay 1
            make_query_response("closed"),  # refresh: relay 2
        ])

        with patch("custom_components.remootio.coordinator.async_dispatcher_send"):
            await mock_coordinator.async_trigger(1)

        mock_coordinator.api.async_send_command.assert_any_call("TRIGGER", 1)


class TestDeviceInfo:
    """Tests for the coordinator's device_info property."""

    def test_device_info(self, mock_coordinator):
        """device_info returns correct DeviceInfo dict."""
        info = mock_coordinator.device_info

        assert info["identifiers"] == {("remootio", TEST_HOST)}
        assert info["name"] == "Test Garage"
        assert info["manufacturer"] == "Remootio"
        assert info["model"] == "Garage Door Controller"
