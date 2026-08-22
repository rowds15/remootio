"""DataUpdateCoordinator for Remootio integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RemootioAPI, RemootioEventListener
from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL,
    SIGNAL_REMOOTIO_STATE_CHANGED,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)


class RemootioCoordinator(DataUpdateCoordinator[dict[int, str | None]]):
    """Coordinator that polls relay 1 and maintains a real-time event listener."""

    # RemootioAPI.async_send_command swallows most communication errors
    # (timeouts, connection failures) and returns None rather than raising,
    # so a real outage shows up here as a falsy QUERY response, not an
    # exception. Tolerate a few in a row (transient blips) before raising
    # UpdateFailed — but once we hit this many consecutive misses, raise so
    # last_update_success flips False and entities go unavailable instead of
    # silently reporting a stale state indefinitely.
    _MAX_CONSECUTIVE_FAILURES = 3

    def __init__(
        self,
        hass: HomeAssistant,
        api: RemootioAPI,
        name: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"Remootio {name}",
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self._device_name = name
        self._previous_states: dict[int, str | None] = {1: None}
        self._listener: RemootioEventListener | None = None
        self._consecutive_failures = 0

    @property
    def host(self) -> str:
        """Return the device host for unique ID construction."""
        return self.api.host

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info shared by all entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.api.host)},
            name=self._device_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    async def async_start_event_listener(self) -> None:
        """Start the persistent WebSocket event listener.

        The listener instance is created once and reused across restarts so
        its event-counter dedup survives the stop/start cycle around TRIGGER
        commands.
        """
        if self._listener is None:
            self._listener = RemootioEventListener(
                self.api, self._handle_event_state_change
            )
        await self._listener.async_start()

    async def async_stop_event_listener(self) -> None:
        """Stop the persistent WebSocket event listener."""
        if self._listener:
            await self._listener.async_stop()

    async def _handle_event_state_change(self, state: str) -> None:
        """Handle a real-time StateChange event from the listener."""
        if state is None:
            return
        old_state = self._previous_states.get(1)
        if old_state == state:
            return

        self._previous_states[1] = state
        new_data = dict(self.data or {})
        new_data[1] = state
        self.async_set_updated_data(new_data)

        if old_state is not None:
            signal = f"{SIGNAL_REMOOTIO_STATE_CHANGED}_{self.api.host}_ch1"
            async_dispatcher_send(self.hass, signal, old_state, state)

    async def _async_update_data(self) -> dict[int, str | None]:
        """Query relay 1 only.

        The Remootio API has no QUERY_SECONDARY — QUERY always returns the
        primary output state.  Relay 2 (secondary) has no queryable state.

        Skips the network call while the event listener holds a live
        connection: the device only accepts one WebSocket connection at a
        time, so opening a second connection for polling would time out
        while the listener holds the persistent one.  When the listener is
        down or reconnecting, polling resumes as a fallback so the state
        can never stay frozen indefinitely.
        """
        if self._listener is not None and self._listener.connected:
            return dict(self._previous_states)

        try:
            result = await self.api.async_send_command("QUERY", 1)
        except Exception as err:
            _LOGGER.warning("Error querying relay 1: %s, keeping previous state", err)
            raise UpdateFailed("Unable to communicate with Remootio device") from err

        if result and result.get("response"):
            state = result["response"].get("state")
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1
            _LOGGER.warning(
                "No response for relay 1 (%d consecutive), keeping previous state",
                self._consecutive_failures,
            )
            if self._consecutive_failures >= self._MAX_CONSECUTIVE_FAILURES:
                raise UpdateFailed(
                    f"No response from Remootio device for "
                    f"{self._consecutive_failures} consecutive polls"
                )
            state = self._previous_states.get(1)

        states: dict[int, str | None] = {1: state}

        old_state = self._previous_states.get(1)
        if old_state is not None and state is not None and old_state != state:
            signal = f"{SIGNAL_REMOOTIO_STATE_CHANGED}_{self.api.host}_ch1"
            async_dispatcher_send(self.hass, signal, old_state, state)

        self._previous_states = dict(states)
        return states

    async def _async_send_exclusive(self, command_type: str, relay_number: int) -> None:
        """Send *command_type* with exclusive WebSocket access.

        Stops the event listener first so the command gets exclusive
        WebSocket access — the device rejects a second concurrent connection.
        No explicit refresh is needed: the restarted listener queries the
        door state as part of its connect handshake, which both syncs any
        change caused by the command and avoids a polling connection racing
        the listener's reconnect.
        """
        await self.async_stop_event_listener()
        try:
            await self.api.async_send_command(command_type, relay_number)
        finally:
            await self.async_start_event_listener()

    async def async_trigger(self, relay_number: int) -> None:
        """Send TRIGGER command.

        TRIGGER always toggles the gate regardless of its current state.
        This is what the non-directional toggle buttons want; the cover
        entity's open/close must NOT use this — see async_open/async_close.
        """
        await self._async_send_exclusive("TRIGGER", relay_number)

    async def async_open(self, relay_number: int) -> None:
        """Send OPEN command.

        Unlike TRIGGER, OPEN/CLOSE are directional and gate on the door's
        current status in firmware, so this is a no-op if the door is
        already open — matching Remootio's own cloud/SmartThings integration.
        """
        await self._async_send_exclusive("OPEN", relay_number)

    async def async_close(self, relay_number: int) -> None:
        """Send CLOSE command. See async_open for why this isn't TRIGGER."""
        await self._async_send_exclusive("CLOSE", relay_number)
