"""DataUpdateCoordinator for Remootio integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RemootioAPI
from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL,
    SIGNAL_REMOOTIO_STATE_CHANGED,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)


class RemootioCoordinator(DataUpdateCoordinator[dict[int, str | None]]):
    """Coordinator that polls both relays and fires dispatcher signals on transitions."""

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

    async def _async_update_data(self) -> dict[int, str | None]:
        """Query relay 1 only.

        The Remootio API has no QUERY_SECONDARY — QUERY always returns the
        primary output state.  Relay 2 (secondary) has no queryable state.
        """
        try:
            result = await self.api.async_send_command("QUERY", 1)
        except Exception as err:
            _LOGGER.warning("Error querying relay 1: %s, keeping previous state", err)
            raise UpdateFailed("Unable to communicate with Remootio device") from err

        if result and result.get("response"):
            state = result["response"].get("state")
        else:
            _LOGGER.warning("No response for relay 1, keeping previous state")
            state = self._previous_states.get(1)

        states: dict[int, str | None] = {1: state}

        # Fire dispatcher signal on relay 1 state transition
        old_state = self._previous_states.get(1)
        if old_state is not None and state is not None and old_state != state:
            signal = f"{SIGNAL_REMOOTIO_STATE_CHANGED}_{self.api.host}_ch1"
            async_dispatcher_send(self.hass, signal, old_state, state)

        self._previous_states = dict(states)
        return states

    async def async_trigger(self, relay_number: int) -> None:
        """Send TRIGGER command and request a data refresh."""
        await self.api.async_send_command("TRIGGER", relay_number)
        await self.async_request_refresh()
