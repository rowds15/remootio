"""Remootio Button Platform for garage door control."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_API_AUTH_KEY,
    CONF_API_SECRET_KEY,
    DEFAULT_NAME,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)
from .cover import RemootioCover

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Remootio buttons from a config entry."""
    host = entry.data[CONF_HOST]
    api_secret_key = entry.data[CONF_API_SECRET_KEY]
    api_auth_key = entry.data[CONF_API_AUTH_KEY]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    buttons = [
        RemootioButton(
            hass=hass,
            device_name=name,
            host=host,
            api_secret_key=api_secret_key,
            api_auth_key=api_auth_key,
            entry_id=entry.entry_id,
            button_type="toggle",
        ),
    ]
    async_add_entities(buttons)


class RemootioButton(ButtonEntity):
    """Button to trigger the Remootio garage door."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        device_name: str,
        host: str,
        api_secret_key: str,
        api_auth_key: str,
        entry_id: str,
        button_type: str,
    ) -> None:
        """Initialize the button."""
        self.hass = hass
        self._device_name = device_name
        self._host = host
        self._api_secret_key = api_secret_key
        self._api_auth_key = api_auth_key
        self._entry_id = entry_id
        self._button_type = button_type

        self._attr_unique_id = f"remootio_{host.replace('.', '_')}_{button_type}"
        self._attr_name = "Toggle"
        self._attr_icon = "mdi:garage"

        # Create a cover instance for sending commands
        self._cover = RemootioCover(
            hass=hass,
            name=device_name,
            host=host,
            api_secret_key=api_secret_key,
            api_auth_key=api_auth_key,
            entry_id=entry_id,
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for device registry."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._host)},
            name=self._device_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Toggle button pressed for %s", self._device_name)
        await self._cover._send_command("TRIGGER")
