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
        self._previous_states: dict[int, str | None] = {1: None, 2: None}

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
        """Query relay 1 then relay 2 sequentially."""
        states: dict[int, str | None] = {}
        failures = 0

        for relay in (1, 2):
            try:
                result = await self.api.async_send_command("QUERY", relay)
                if result and result.get("response"):
                    state = result["response"].get("state")
                    states[relay] = state
                else:
                    # Fall back to previous known state on per-relay error
                    states[relay] = self._previous_states.get(relay)
                    failures += 1
            except Exception as err:
                _LOGGER.debug(
                    "Error querying relay %d: %s, keeping previous state", relay, err
                )
                states[relay] = self._previous_states.get(relay)
                failures += 1

        # If both relays failed, raise so CoordinatorEntity marks entities unavailable
        if failures >= 2:
            raise UpdateFailed("Unable to communicate with Remootio device")

        # Fire dispatcher signals on state transitions
        for relay in (1, 2):
            old_state = self._previous_states.get(relay)
            new_state = states[relay]
            if old_state is not None and new_state is not None and old_state != new_state:
                signal = f"{SIGNAL_REMOOTIO_STATE_CHANGED}_{self.api.host}_ch{relay}"
                async_dispatcher_send(self.hass, signal, old_state, new_state)

        self._previous_states = dict(states)
        return states

    async def async_trigger(self, relay_number: int) -> None:
        """Send TRIGGER command and request a data refresh."""
        await self.api.async_send_command("TRIGGER", relay_number)
        await self.async_request_refresh()
