"""DataUpdateCoordinator for Remootio integration."""
from __future__ import annotations

import asyncio
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
    """Coordinator that polls relay 1 and maintains a real-time event listener.

    Two independent mechanisms tolerate a flaky device, at different layers
    and for different reasons — they're intentionally not unified:

    - ``RemootioEventListener`` (api.py) uses a time-based exponential
      backoff to keep retrying its own WebSocket reconnect indefinitely.
      That's about the listener staying alive, not about entity state.
    - ``_MAX_CONSECUTIVE_FAILURES`` below is a poll-count threshold that
      decides when *entities* should stop trusting the cached state and go
      unavailable. It only applies to the polling fallback path, since a
      connected listener already proves liveness on its own (see
      ``_async_update_data``).
    """

    # RemootioAPI.async_send_command swallows most communication errors
    # (timeouts, connection failures) and returns None rather than raising,
    # so a real outage shows up here as a falsy/invalid QUERY response, not
    # an exception. Tolerate a few in a row (transient blips) before raising
    # UpdateFailed — but once we hit this many consecutive misses, raise so
    # last_update_success flips False and entities go unavailable instead of
    # silently reporting a stale state indefinitely.
    #
    # This threshold only governs that soft-failure path. A hard exception
    # (CannotConnect/InvalidAuth, raised when the auth handshake itself
    # fails — e.g. wrong keys or an unexpected protocol response) is a
    # configuration-level error that won't self-heal by retrying, so it
    # deliberately raises UpdateFailed immediately rather than waiting out
    # this same tolerance window.
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
        # Serializes TRIGGER/OPEN/CLOSE against the poller: both stop the
        # listener to get exclusive WebSocket access, and the device only
        # accepts one connection at a time. See _async_send_exclusive and
        # the poll-skip check in _async_update_data.
        self._command_lock = asyncio.Lock()

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
        its event-counter dedup survives the stop/start cycle around
        exclusive commands (TRIGGER/OPEN/CLOSE).
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

        # A delivered event proves the listener has live connectivity right
        # now, regardless of whether the state actually changed — reset the
        # poll-failure streak so a stale count from an earlier blip can't
        # combine with a later, unrelated poll miss to trip the threshold.
        self._consecutive_failures = 0

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

        A missing/invalid response is tolerated for up to
        ``_MAX_CONSECUTIVE_FAILURES`` consecutive polls (a transient blip
        keeps serving the cached state); beyond that this raises
        ``UpdateFailed``, which HA turns into ``last_update_success = False``
        so dependent entities go unavailable instead of reporting a stale
        state through an extended outage.
        """
        if self._listener is not None and self._listener.connected:
            # A live, authenticated listener connection is itself proof the
            # device is reachable right now.
            self._consecutive_failures = 0
            return dict(self._previous_states)

        if self._command_lock.locked():
            # An exclusive command (TRIGGER/OPEN/CLOSE) currently has the
            # listener stopped for exclusive WebSocket access — skip this
            # cycle rather than race it with a second connection. This is
            # neither a success nor a failure, so the streak is left as-is.
            return dict(self._previous_states)

        async with self._command_lock:
            try:
                result = await self.api.async_send_command("QUERY", 1)
            except Exception as err:
                _LOGGER.warning(
                    "Error querying relay 1: %s — marking update failed", err
                )
                raise UpdateFailed("Unable to communicate with Remootio device") from err

        response = result.get("response") if result else None
        # Require an explicit state and no explicit failure flag — a present
        # but malformed response (e.g. missing "state") is just as much a
        # failure as no response at all, and must not be treated as a
        # successful poll (which would wipe out the last known door state).
        if response and response.get("state") is not None and response.get("success", True):
            state = response.get("state")
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1
            _LOGGER.warning(
                "Invalid or missing response for relay 1 (%d consecutive), "
                "keeping previous state",
                self._consecutive_failures,
            )
            if self._consecutive_failures >= self._MAX_CONSECUTIVE_FAILURES:
                raise UpdateFailed(
                    f"No valid response from Remootio device for "
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
        Holds ``_command_lock`` for the same reason against the poller, and
        to serialize overlapping command calls (e.g. a rapid double press)
        so they can't both try to stop/restart the listener at once.  No
        explicit refresh is needed: the restarted listener queries the door
        state as part of its connect handshake, which both syncs any change
        caused by the command and avoids a polling connection racing the
        listener's reconnect.
        """
        result: dict | None = None
        async with self._command_lock:
            await self.async_stop_event_listener()
            try:
                result = await self.api.async_send_command(command_type, relay_number)
            finally:
                await self.async_start_event_listener()

        # The response is otherwise unused (fire-and-forget) — the listener's
        # reconnect QUERY is what syncs door state — but a device-side
        # rejection or dropped response would otherwise fail completely
        # silently.
        if result is None:
            _LOGGER.warning(
                "%s command to relay %d got no response from the device",
                command_type,
                relay_number,
            )
        elif result.get("response", {}).get("success") is False:
            _LOGGER.warning(
                "%s command to relay %d was rejected by the device",
                command_type,
                relay_number,
            )

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

        Only relay 1 (the primary output) supports OPEN — the API has no
        directional action for the secondary relay, only TRIGGER_SECONDARY.
        """
        if relay_number != 1:
            raise ValueError(
                "OPEN is only supported on relay 1 — Remootio has no "
                "directional action for the secondary relay"
            )
        await self._async_send_exclusive("OPEN", relay_number)

    async def async_close(self, relay_number: int) -> None:
        """Send CLOSE command. See async_open for why this isn't TRIGGER.

        Only relay 1 (the primary output) supports CLOSE — see async_open.
        """
        if relay_number != 1:
            raise ValueError(
                "CLOSE is only supported on relay 1 — Remootio has no "
                "directional action for the secondary relay"
            )
        await self._async_send_exclusive("CLOSE", relay_number)
