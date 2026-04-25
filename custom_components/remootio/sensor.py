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

    # Relay 2 (secondary) has no queryable state in the Remootio API, so
    # state-change signals for ch2 are never fired.  Only relay 1 gets sensors.
    sensors: list[SensorEntity] = [
        RemootioOperationCountSensor(coordinator, relay_number=1),
        RemootioLastOpenedSensor(coordinator, relay_number=1),
        RemootioLastClosedSensor(coordinator, relay_number=1),
    ]

    async_add_entities(sensors)


class _RemootioSensorBase(SensorEntity):
    """Base class for all Remootio sensor entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RemootioCoordinator,
        relay_number: int,
        uid_suffix: str,
        translation_key_prefix: str,
    ) -> None:
        """Initialize the sensor base."""
        self._coordinator = coordinator
        self._relay_number = relay_number
        self._attr_unique_id = (
            f"remootio_{coordinator.host.replace('.', '_')}_{uid_suffix}_ch{relay_number}"
        )
        self._attr_translation_key = f"{translation_key_prefix}_{relay_number}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for device registry."""
        return self._coordinator.device_info

    async def async_added_to_hass(self) -> None:
        """Subscribe to dispatcher signal for state transitions."""
        await super().async_added_to_hass()
        signal = f"{SIGNAL_REMOOTIO_STATE_CHANGED}_{self._coordinator.host}_ch{self._relay_number}"
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._handle_state_changed)
        )

    @callback
    def _handle_state_changed(self, old_state: str, new_state: str) -> None:
        """Handle a state transition — subclasses must override."""
        raise NotImplementedError


class RemootioOperationCountSensor(RestoreEntity, _RemootioSensorBase):
    """Sensor that counts how many times the garage door has been opened."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: RemootioCoordinator, relay_number: int) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, relay_number, "operation_count", "operation_count_channel")
        self._count: int = 0

    @property
    def native_value(self) -> int:
        """Return the current count."""
        return self._count

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to dispatcher signal."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                self._count = int(last_state.state)
            except (ValueError, TypeError):
                self._count = 0

    @callback
    def _handle_state_changed(self, old_state: str, new_state: str) -> None:
        """Handle a state transition from the cover."""
        if new_state == "open":
            self._count += 1
            self.async_write_ha_state()


class RemootioLastOpenedSensor(_RemootioSensorBase):
    """Sensor that records when the garage door was last opened."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:garage-open"

    def __init__(self, coordinator: RemootioCoordinator, relay_number: int) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, relay_number, "last_opened", "last_opened_channel")
        self._timestamp = None

    @property
    def native_value(self):
        """Return the last opened timestamp."""
        return self._timestamp

    @callback
    def _handle_state_changed(self, old_state: str, new_state: str) -> None:
        """Handle a state transition from the cover."""
        if new_state == "open":
            self._timestamp = dt_util.utcnow()
            self.async_write_ha_state()


class RemootioLastClosedSensor(_RemootioSensorBase):
    """Sensor that records when the garage door was last closed."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:garage"

    def __init__(self, coordinator: RemootioCoordinator, relay_number: int) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, relay_number, "last_closed", "last_closed_channel")
        self._timestamp = None

    @property
    def native_value(self):
        """Return the last closed timestamp."""
        return self._timestamp

    @callback
    def _handle_state_changed(self, old_state: str, new_state: str) -> None:
        """Handle a state transition from the cover."""
        if new_state == "closed":
            self._timestamp = dt_util.utcnow()
            self.async_write_ha_state()
