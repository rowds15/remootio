"""Remootio Sensor Platform for garage door activity tracking."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SIGNAL_REMOOTIO_STATE_CHANGED
from .coordinator import RemootioCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Remootio sensors from a config entry."""
    coordinator: RemootioCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors: list[SensorEntity] = []
    for relay_number in (1, 2):
        sensors.extend([
            RemootioOperationCountSensor(coordinator, relay_number),
            RemootioLastOpenedSensor(coordinator, relay_number),
            RemootioLastClosedSensor(coordinator, relay_number),
        ])

    async_add_entities(sensors)


class RemootioOperationCountSensor(RestoreEntity, SensorEntity):
    """Sensor that counts how many times the garage door has been opened."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: RemootioCoordinator, relay_number: int) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._relay_number = relay_number
        self._attr_unique_id = (
            f"remootio_{coordinator.host.replace('.', '_')}_operation_count_ch{relay_number}"
        )
        self._attr_name = f"Operation Count Channel {relay_number}"
        self._count: int = 0

    @property
    def native_value(self) -> int:
        """Return the current count."""
        return self._count

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for device registry."""
        return self._coordinator.device_info

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to dispatcher signal."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                self._count = int(last_state.state)
            except (ValueError, TypeError):
                self._count = 0

        signal = f"{SIGNAL_REMOOTIO_STATE_CHANGED}_{self._coordinator.host}_ch{self._relay_number}"
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._handle_state_changed)
        )

    @callback
    def _handle_state_changed(self, old_state: str, new_state: str) -> None:
        """Handle a state transition from the cover."""
        if new_state == "open":
            self._count += 1
            self.async_write_ha_state()


class RemootioLastOpenedSensor(SensorEntity):
    """Sensor that records when the garage door was last opened."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:garage-open"

    def __init__(self, coordinator: RemootioCoordinator, relay_number: int) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._relay_number = relay_number
        self._attr_unique_id = (
            f"remootio_{coordinator.host.replace('.', '_')}_last_opened_ch{relay_number}"
        )
        self._attr_name = f"Last Opened Channel {relay_number}"
        self._timestamp = None

    @property
    def native_value(self):
        """Return the last opened timestamp."""
        return self._timestamp

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for device registry."""
        return self._coordinator.device_info

    async def async_added_to_hass(self) -> None:
        """Subscribe to dispatcher signal."""
        signal = f"{SIGNAL_REMOOTIO_STATE_CHANGED}_{self._coordinator.host}_ch{self._relay_number}"
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._handle_state_changed)
        )

    @callback
    def _handle_state_changed(self, old_state: str, new_state: str) -> None:
        """Handle a state transition from the cover."""
        if new_state == "open":
            self._timestamp = dt_util.utcnow()
            self.async_write_ha_state()


class RemootioLastClosedSensor(SensorEntity):
    """Sensor that records when the garage door was last closed."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:garage"

    def __init__(self, coordinator: RemootioCoordinator, relay_number: int) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._relay_number = relay_number
        self._attr_unique_id = (
            f"remootio_{coordinator.host.replace('.', '_')}_last_closed_ch{relay_number}"
        )
        self._attr_name = f"Last Closed Channel {relay_number}"
        self._timestamp = None

    @property
    def native_value(self):
        """Return the last closed timestamp."""
        return self._timestamp

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for device registry."""
        return self._coordinator.device_info

    async def async_added_to_hass(self) -> None:
        """Subscribe to dispatcher signal."""
        signal = f"{SIGNAL_REMOOTIO_STATE_CHANGED}_{self._coordinator.host}_ch{self._relay_number}"
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._handle_state_changed)
        )

    @callback
    def _handle_state_changed(self, old_state: str, new_state: str) -> None:
        """Handle a state transition from the cover."""
        if new_state == "closed":
            self._timestamp = dt_util.utcnow()
            self.async_write_ha_state()
