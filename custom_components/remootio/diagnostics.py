"""Diagnostics support for Remootio integration."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_AUTH_KEY, CONF_API_SECRET_KEY, DOMAIN

REDACTED = "**REDACTED**"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Redact sensitive keys from entry data
    redacted_data = dict(entry.data)
    for key in (CONF_API_SECRET_KEY, CONF_API_AUTH_KEY):
        if key in redacted_data:
            redacted_data[key] = REDACTED

    return {
        "entry_data": redacted_data,
        "device_name": coordinator._device_name,
        "host": coordinator.api.host,
        "relay_states": coordinator.data,
        "update_interval_seconds": coordinator.update_interval.total_seconds(),
        "last_update_success": coordinator.last_update_success,
    }
