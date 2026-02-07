"""Config flow for Remootio integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME

from .api import CannotConnect, InvalidAuth, RemootioAPI
from .const import (
    CONF_API_AUTH_KEY,
    CONF_API_SECRET_KEY,
    DEFAULT_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_API_SECRET_KEY): str,
        vol.Required(CONF_API_AUTH_KEY): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
    }
)


async def validate_input(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    api = RemootioAPI(
        host=data[CONF_HOST],
        api_secret_key=data[CONF_API_SECRET_KEY],
        api_auth_key=data[CONF_API_AUTH_KEY],
    )
    await api.async_validate_connection()
    return {"title": data.get(CONF_NAME, DEFAULT_NAME)}


class RemootioConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Remootio."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip().lower()

            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            try:
                info = await validate_input(user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip().lower()

            try:
                info = await validate_input(user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates=user_input,
                )

        reconfigure_entry = self._get_reconfigure_entry()
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST, default=reconfigure_entry.data.get(CONF_HOST, "")
                    ): str,
                    vol.Required(CONF_API_SECRET_KEY): str,
                    vol.Required(CONF_API_AUTH_KEY): str,
                    vol.Optional(
                        CONF_NAME,
                        default=reconfigure_entry.data.get(CONF_NAME, DEFAULT_NAME),
                    ): str,
                }
            ),
            errors=errors,
        )
