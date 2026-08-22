"""Tests for custom_components.remootio.coordinator."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.remootio.coordinator import RemootioCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed
from tests.conftest import TEST_HOST, make_query_response


class TestAsyncUpdateData:
    """Tests for the coordinator's _async_update_data method."""

    @pytest.mark.asyncio
    async def test_update_relay1_success(self, mock_coordinator):
        """Relay 1 returns a valid state."""
        mock_coordinator.api.async_send_command = AsyncMock(return_value=make_query_response("open"))

        result = await mock_coordinator._async_update_data()

        assert result == {1: "open"}

    @pytest.mark.asyncio
    async def test_update_relay1_returns_none_falls_back_to_previous(self, mock_coordinator):
        """A single soft failure falls back to previous state without raising."""
        mock_coordinator._previous_states = {1: "closed"}
        mock_coordinator.api.async_send_command = AsyncMock(return_value=None)

        result = await mock_coordinator._async_update_data()

        assert result == {1: "closed"}

    @pytest.mark.asyncio
    async def test_update_raises_after_max_consecutive_soft_failures(self, mock_coordinator):
        """A None/empty response with no exception must eventually mark the
        coordinator failed — otherwise a real outage (the device unreachable,
        but async_send_command swallowing the error and returning None) never
        raises UpdateFailed and entities stay available showing stale data
        forever. Confirmed via a 45-hour real-world outage."""
        mock_coordinator._previous_states = {1: "closed"}
        mock_coordinator.api.async_send_command = AsyncMock(return_value=None)

        for _ in range(mock_coordinator._MAX_CONSECUTIVE_FAILURES - 1):
            result = await mock_coordinator._async_update_data()
            assert result == {1: "closed"}  # still soft-failing, no raise yet

        with pytest.raises(UpdateFailed):
            await mock_coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_update_resets_failure_counter_on_success(self, mock_coordinator):
        """A successful poll in between resets the consecutive-failure count,
        so a single blip doesn't count towards the next outage's threshold."""
        mock_coordinator._previous_states = {1: "closed"}
        mock_coordinator.api.async_send_command = AsyncMock(
            side_effect=[None, None, make_query_response("closed"), None, None]
        )

        for _ in range(5):
            await mock_coordinator._async_update_data()

        assert mock_coordinator._consecutive_failures == 2

    @pytest.mark.asyncio
    async def test_update_raises_update_failed_when_command_raises(self, mock_coordinator):
        """When async_send_command raises, coordinator raises UpdateFailed."""
        mock_coordinator.api.async_send_command = AsyncMock(side_effect=OSError("network error"))

        with pytest.raises(UpdateFailed):
            await mock_coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_update_skips_poll_while_listener_connected(self, mock_coordinator):
        """A live event listener holds the only allowed connection — no poll."""
        mock_coordinator._previous_states = {1: "open"}
        mock_coordinator._listener = MagicMock(connected=True)
        mock_coordinator.api.async_send_command = AsyncMock()

        result = await mock_coordinator._async_update_data()

        assert result == {1: "open"}
        mock_coordinator.api.async_send_command.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_polls_when_listener_disconnected(self, mock_coordinator):
        """Polling resumes as a fallback while the listener is reconnecting."""
        mock_coordinator._previous_states = {1: "open"}
        mock_coordinator._listener = MagicMock(connected=False)
        mock_coordinator.api.async_send_command = AsyncMock(
            return_value=make_query_response("closed")
        )

        with patch("custom_components.remootio.coordinator.async_dispatcher_send"):
            result = await mock_coordinator._async_update_data()

        assert result == {1: "closed"}
        mock_coordinator.api.async_send_command.assert_awaited_once_with("QUERY", 1)


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
        """async_trigger stops the listener, sends TRIGGER, restarts the listener."""
        mock_coordinator.api.async_send_command = AsyncMock(return_value=None)
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_stop = AsyncMock()
        mock_coordinator._listener = mock_listener

        await mock_coordinator.async_trigger(1)

        mock_coordinator.api.async_send_command.assert_awaited_once_with("TRIGGER", 1)
        mock_listener.async_stop.assert_awaited_once()
        mock_listener.async_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_trigger_restarts_listener_on_command_error(self, mock_coordinator):
        """Listener is restarted even when the TRIGGER command raises."""
        mock_coordinator.api.async_send_command = AsyncMock(side_effect=OSError("boom"))
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_stop = AsyncMock()
        mock_coordinator._listener = mock_listener

        with pytest.raises(OSError):
            await mock_coordinator.async_trigger(1)

        mock_listener.async_start.assert_awaited_once()


class TestAsyncOpenClose:
    """Tests for the coordinator's directional async_open/async_close methods.

    OPEN/CLOSE gate on gate status in firmware (unlike TRIGGER, which just
    toggles), so cover.py must use these instead of async_trigger for
    open_cover/close_cover to be idempotent.
    """

    @pytest.mark.asyncio
    async def test_async_open_sends_open_command(self, mock_coordinator):
        """async_open stops the listener, sends OPEN, restarts the listener."""
        mock_coordinator.api.async_send_command = AsyncMock(return_value=None)
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_stop = AsyncMock()
        mock_coordinator._listener = mock_listener

        await mock_coordinator.async_open(1)

        mock_coordinator.api.async_send_command.assert_awaited_once_with("OPEN", 1)
        mock_listener.async_stop.assert_awaited_once()
        mock_listener.async_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_close_sends_close_command(self, mock_coordinator):
        """async_close stops the listener, sends CLOSE, restarts the listener."""
        mock_coordinator.api.async_send_command = AsyncMock(return_value=None)
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_stop = AsyncMock()
        mock_coordinator._listener = mock_listener

        await mock_coordinator.async_close(1)

        mock_coordinator.api.async_send_command.assert_awaited_once_with("CLOSE", 1)
        mock_listener.async_stop.assert_awaited_once()
        mock_listener.async_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_open_restarts_listener_on_command_error(self, mock_coordinator):
        """Listener is restarted even when the OPEN command raises."""
        mock_coordinator.api.async_send_command = AsyncMock(side_effect=OSError("boom"))
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_stop = AsyncMock()
        mock_coordinator._listener = mock_listener

        with pytest.raises(OSError):
            await mock_coordinator.async_open(1)

        mock_listener.async_start.assert_awaited_once()


class TestEventListenerLifecycle:
    """Tests for listener start/stop methods."""

    @pytest.mark.asyncio
    async def test_async_start_event_listener_creates_listener(self, mock_coordinator):
        """async_start_event_listener creates and starts a RemootioEventListener."""
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()

        with patch(
            "custom_components.remootio.coordinator.RemootioEventListener",
            return_value=mock_listener,
        ) as mock_cls:
            await mock_coordinator.async_start_event_listener()

        mock_cls.assert_called_once_with(
            mock_coordinator.api, mock_coordinator._handle_event_state_change
        )
        mock_listener.async_start.assert_awaited_once()
        assert mock_coordinator._listener is mock_listener

    @pytest.mark.asyncio
    async def test_async_start_event_listener_reuses_instance(self, mock_coordinator):
        """A second start reuses the existing listener (keeps event-cnt dedup)."""
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_coordinator._listener = mock_listener

        await mock_coordinator.async_start_event_listener()

        assert mock_coordinator._listener is mock_listener
        mock_listener.async_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_stop_event_listener_stops_and_keeps_instance(self, mock_coordinator):
        """async_stop_event_listener stops the listener but keeps the instance."""
        mock_listener = MagicMock()
        mock_listener.async_stop = AsyncMock()
        mock_coordinator._listener = mock_listener

        await mock_coordinator.async_stop_event_listener()

        mock_listener.async_stop.assert_awaited_once()
        assert mock_coordinator._listener is mock_listener

    @pytest.mark.asyncio
    async def test_async_stop_event_listener_noop_when_none(self, mock_coordinator):
        """async_stop_event_listener does nothing if no listener is running."""
        mock_coordinator._listener = None
        await mock_coordinator.async_stop_event_listener()  # must not raise


class TestHandleEventStateChange:
    """Tests for the real-time event callback."""

    @pytest.mark.asyncio
    async def test_state_change_updates_data_and_fires_signal(self, mock_coordinator):
        """New state updates coordinator.data and fires dispatcher signal."""
        mock_coordinator._previous_states = {1: "closed"}
        mock_coordinator.data = {1: "closed"}

        with patch("custom_components.remootio.coordinator.async_dispatcher_send") as mock_send:
            await mock_coordinator._handle_event_state_change("open")

        assert mock_coordinator.data[1] == "open"
        assert mock_coordinator._previous_states[1] == "open"
        mock_send.assert_called_once_with(
            mock_coordinator.hass,
            f"remootio_state_changed_{TEST_HOST}_ch1",
            "closed",
            "open",
        )

    @pytest.mark.asyncio
    async def test_no_signal_when_state_unchanged(self, mock_coordinator):
        """No dispatcher signal when event delivers same state as current."""
        mock_coordinator._previous_states = {1: "open"}
        mock_coordinator.data = {1: "open"}

        with patch("custom_components.remootio.coordinator.async_dispatcher_send") as mock_send:
            await mock_coordinator._handle_event_state_change("open")

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_signal_on_first_event_when_previous_none(self, mock_coordinator):
        """First event (previous state is None) updates data but fires no signal."""
        mock_coordinator._previous_states = {1: None}
        mock_coordinator.data = {}

        with patch("custom_components.remootio.coordinator.async_dispatcher_send") as mock_send:
            await mock_coordinator._handle_event_state_change("open")

        assert mock_coordinator.data[1] == "open"
        mock_send.assert_not_called()


class TestDeviceInfo:
    """Tests for the coordinator's device_info property."""

    def test_device_info(self, mock_coordinator):
        """device_info returns correct DeviceInfo dict."""
        info = mock_coordinator.device_info

        assert info["identifiers"] == {("remootio", TEST_HOST)}
        assert info["name"] == "Test Garage"
        assert info["manufacturer"] == "Remootio"
        assert info["model"] == "Garage Door Controller"
