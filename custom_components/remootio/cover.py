"""Remootio Cover Platform."""
from __future__ import annotations

import logging

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RemootioCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Remootio covers from a config entry."""
    coordinator: RemootioCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([RemootioCover(coordinator, relay_number=1)])


class RemootioCover(CoordinatorEntity[RemootioCoordinator], CoverEntity):
    """Representation of a Remootio cover."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.GARAGE
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(self, coordinator: RemootioCoordinator, relay_number: int) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        self._relay_number = relay_number
        self._attr_unique_id = (
            f"remootio_{coordinator.host.replace('.', '_')}_ch{relay_number}"
        )
        self._attr_translation_key = f"channel_{relay_number}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for device registry."""
        return self.coordinator.device_info

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        state = self.coordinator.data.get(self._relay_number)
        if state is None:
            return None
        return state == "closed"

    @property
    def is_open(self) -> bool | None:
        """Return if the cover is open."""
        state = self.coordinator.data.get(self._relay_number)
        if state is None:
            return None
        return state == "open"

    async def async_open_cover(self, **kwargs) -> None:
        """Open the cover."""
        await self.coordinator.async_trigger(self._relay_number)

    async def async_close_cover(self, **kwargs) -> None:
        """Close the cover."""
        await self.coordinator.async_trigger(self._relay_number)
