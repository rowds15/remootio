"""Remootio Custom Integration."""
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "remootio_custom"


async def async_setup(hass, config):
    """Set up the Remootio Custom component."""
    return True


async def async_setup_entry(hass, entry):
    """Set up Remootio from a config entry."""
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "cover")
    )
    return True
