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
        """When async_send_command raises, coordinator raises UpdateFailed
        immediately — a hard exception (e.g. bad auth keys) is a config
        error that won't self-heal, so it bypasses the soft-failure
        tolerance rather than waiting out _MAX_CONSECUTIVE_FAILURES."""
        mock_coordinator.api.async_send_command = AsyncMock(side_effect=OSError("network error"))

        with pytest.raises(UpdateFailed):
            await mock_coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_update_response_missing_state_key_is_a_failure(self, mock_coordinator):
        """A present-but-malformed response (no 'state' key) must be treated
        as a failure, not a success — otherwise it both resets the failure
        streak and wipes the last known door state from one bad frame."""
        mock_coordinator._previous_states = {1: "closed"}
        mock_coordinator._consecutive_failures = 1
        mock_coordinator.api.async_send_command = AsyncMock(return_value={"response": {}})

        result = await mock_coordinator._async_update_data()

        assert result == {1: "closed"}
        assert mock_coordinator._consecutive_failures == 2

    @pytest.mark.asyncio
    async def test_update_response_success_false_is_a_failure(self, mock_coordinator):
        """A response with an explicit success:false must not be trusted
        even though it carries a 'state' value."""
        mock_coordinator._previous_states = {1: "closed"}
        mock_coordinator.api.async_send_command = AsyncMock(
            return_value={"response": {"state": "open", "success": False}}
        )

        result = await mock_coordinator._async_update_data()

        assert result == {1: "closed"}
        assert mock_coordinator._consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_update_skips_poll_while_listener_connected(self, mock_coordinator):
        """A live event listener holds the only allowed connection — no poll."""
        mock_coordinator._previous_states = {1: "open"}
        mock_coordinator._listener = MagicMock(connected=True, seconds_idle=0)
        mock_coordinator.api.async_send_command = AsyncMock()

        result = await mock_coordinator._async_update_data()

        assert result == {1: "open"}
        mock_coordinator.api.async_send_command.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_listener_connected_resets_failure_streak(self, mock_coordinator):
        """A live listener connection proves the device is reachable, so it
        must reset a failure streak accumulated before the listener came up
        — otherwise it can combine with a later, unrelated poll miss to trip
        the unavailable threshold on what's really the first real failure."""
        mock_coordinator._previous_states = {1: "open"}
        mock_coordinator._consecutive_failures = 2
        mock_coordinator._listener = MagicMock(connected=True, seconds_idle=0)

        await mock_coordinator._async_update_data()

        assert mock_coordinator._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_update_polls_when_listener_connected_but_stale(self, mock_coordinator):
        """A listener that still reports connected but has received nothing
        for longer than the stale threshold must not block polling — a
        half-open TCP connection can leave 'connected' stuck True long after
        the listener has actually stopped delivering anything. Polling is
        the only mechanism left that can notice and recover."""
        mock_coordinator._previous_states = {1: "open"}
        mock_coordinator._listener = MagicMock(
            connected=True,
            seconds_idle=mock_coordinator._STALE_LISTENER_SECONDS + 1,
        )
        mock_coordinator.api.async_send_command = AsyncMock(
            return_value=make_query_response("closed")
        )

        with patch("custom_components.remootio.coordinator.async_dispatcher_send"):
            result = await mock_coordinator._async_update_data()

        assert result == {1: "closed"}
        mock_coordinator.api.async_send_command.assert_awaited_once_with("QUERY", 1)

    @pytest.mark.asyncio
    async def test_update_skips_poll_while_command_lock_held(self, mock_coordinator):
        """An in-flight TRIGGER/OPEN/CLOSE has the listener stopped for
        exclusive access — polling must not race it with a second
        connection, and skipping must not itself count as a failure."""
        mock_coordinator._previous_states = {1: "open"}
        mock_coordinator._consecutive_failures = 1
        mock_coordinator.api.async_send_command = AsyncMock()
        await mock_coordinator._command_lock.acquire()
        try:
            result = await mock_coordinator._async_update_data()
        finally:
            mock_coordinator._command_lock.release()

        assert result == {1: "open"}
        assert mock_coordinator._consecutive_failures == 1
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


class TestExclusiveCommands:
    """Tests for async_trigger/async_open/async_close.

    All three funnel through _async_send_exclusive with the same
    stop-listener/send/restart-listener contract, so they're parametrized
    here rather than duplicated per method. OPEN/CLOSE additionally gate on
    gate status in firmware (unlike TRIGGER, which just toggles), so
    cover.py uses these instead of async_trigger for open_cover/close_cover
    to be idempotent.
    """

    @pytest.mark.parametrize(
        "method_name,command_type",
        [
            ("async_trigger", "TRIGGER"),
            ("async_open", "OPEN"),
            ("async_close", "CLOSE"),
        ],
    )
    @pytest.mark.asyncio
    async def test_sends_expected_command(self, mock_coordinator, method_name, command_type):
        """Stops the listener, sends the expected command, restarts the listener."""
        mock_coordinator.api.async_send_command = AsyncMock(return_value=None)
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_stop = AsyncMock()
        mock_coordinator._listener = mock_listener

        await getattr(mock_coordinator, method_name)(1)

        mock_coordinator.api.async_send_command.assert_awaited_once_with(command_type, 1)
        mock_listener.async_stop.assert_awaited_once()
        mock_listener.async_start.assert_awaited_once()

    @pytest.mark.parametrize("method_name", ["async_trigger", "async_open", "async_close"])
    @pytest.mark.asyncio
    async def test_restarts_listener_on_command_error(self, mock_coordinator, method_name):
        """Listener is restarted even when the command raises."""
        mock_coordinator.api.async_send_command = AsyncMock(side_effect=OSError("boom"))
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_stop = AsyncMock()
        mock_coordinator._listener = mock_listener

        with pytest.raises(OSError):
            await getattr(mock_coordinator, method_name)(1)

        mock_listener.async_start.assert_awaited_once()

    @pytest.mark.parametrize("method_name", ["async_trigger", "async_open", "async_close"])
    @pytest.mark.asyncio
    async def test_logs_warning_on_no_response(self, mock_coordinator, method_name):
        """A None result (device unreachable/dropped) is otherwise silent —
        fire-and-forget commands must still surface it in the log."""
        mock_coordinator.api.async_send_command = AsyncMock(return_value=None)
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_stop = AsyncMock()
        mock_coordinator._listener = mock_listener

        with patch("custom_components.remootio.coordinator._LOGGER") as mock_logger:
            await getattr(mock_coordinator, method_name)(1)

        assert mock_logger.warning.called
        assert "no response" in mock_logger.warning.call_args[0][0].lower()

    @pytest.mark.parametrize("method_name", ["async_trigger", "async_open", "async_close"])
    @pytest.mark.asyncio
    async def test_logs_warning_on_device_rejection(self, mock_coordinator, method_name):
        """A response with success:false means the device rejected the
        command — that must not pass silently."""
        mock_coordinator.api.async_send_command = AsyncMock(
            return_value={"response": {"success": False}}
        )
        mock_listener = MagicMock()
        mock_listener.async_start = AsyncMock()
        mock_listener.async_stop = AsyncMock()
        mock_coordinator._listener = mock_listener

        with patch("custom_components.remootio.coordinator._LOGGER") as mock_logger:
            await getattr(mock_coordinator, method_name)(1)

        assert mock_logger.warning.called
        assert "rejected" in mock_logger.warning.call_args[0][0].lower()


class TestDirectionalCommandsRejectSecondaryRelay:
    """async_open/async_close must refuse relay 2: Remootio has no
    directional action for the secondary relay, only TRIGGER_SECONDARY —
    silently sending a raw OPEN/CLOSE there would have undefined behavior.
    """

    @pytest.mark.parametrize("method_name", ["async_open", "async_close"])
    @pytest.mark.asyncio
    async def test_rejects_relay_2(self, mock_coordinator, method_name):
        mock_coordinator.api.async_send_command = AsyncMock()

        with pytest.raises(ValueError):
            await getattr(mock_coordinator, method_name)(2)

        mock_coordinator.api.async_send_command.assert_not_awaited()


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

    @pytest.mark.asyncio
    async def test_delivered_event_resets_failure_streak(self, mock_coordinator):
        """Any delivered event proves live connectivity right now, even when
        it repeats the current state — it must reset a failure streak
        accumulated before the listener reconnected."""
        mock_coordinator._previous_states = {1: "open"}
        mock_coordinator.data = {1: "open"}
        mock_coordinator._consecutive_failures = 2

        with patch("custom_components.remootio.coordinator.async_dispatcher_send"):
            await mock_coordinator._handle_event_state_change("open")

        assert mock_coordinator._consecutive_failures == 0


class TestDeviceInfo:
    """Tests for the coordinator's device_info property."""

    def test_device_info(self, mock_coordinator):
        """device_info returns correct DeviceInfo dict."""
        info = mock_coordinator.device_info

        assert info["identifiers"] == {("remootio", TEST_HOST)}
        assert info["name"] == "Test Garage"
        assert info["manufacturer"] == "Remootio"
        assert info["model"] == "Garage Door Controller"
