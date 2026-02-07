"""Remootio Integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, Platform
from homeassistant.core import HomeAssistant

from .api import RemootioAPI
from .const import (
    CONF_API_AUTH_KEY,
    CONF_API_SECRET_KEY,
    DEFAULT_NAME,
    DOMAIN,
)
from .coordinator import RemootioCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.COVER, Platform.BUTTON, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Remootio from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    api = RemootioAPI(
        host=entry.data[CONF_HOST],
        api_secret_key=entry.data[CONF_API_SECRET_KEY],
        api_auth_key=entry.data[CONF_API_AUTH_KEY],
    )
    coordinator = RemootioCoordinator(
        hass,
        api,
        name=entry.data.get(CONF_NAME, DEFAULT_NAME),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
