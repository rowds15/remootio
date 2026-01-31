"""Config flow for Remootio integration."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from base64 import b64decode, b64encode
from typing import Any

import voluptuous as vol
import websockets
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME

from .const import (
    CONF_API_AUTH_KEY,
    CONF_API_SECRET_KEY,
    DEFAULT_NAME,
    DEFAULT_PORT,
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


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


def decrypt_frame(encrypted_frame: dict, key: str) -> dict | None:
    """Decrypt a frame using AES-CBC."""
    try:
        key_bytes = bytes.fromhex(key)
        iv = b64decode(encrypted_frame["iv"])
        ciphertext = b64decode(encrypted_frame["payload"])

        cipher = Cipher(
            algorithms.AES(key_bytes), modes.CBC(iv), backend=default_backend()
        )
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        padding_length = padded_plaintext[-1]
        plaintext = padded_plaintext[:-padding_length]

        return json.loads(plaintext.decode("utf-8"))
    except Exception as err:
        _LOGGER.debug("Decryption error: %s", err)
        return None


async def validate_input(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    host = data[CONF_HOST]
    api_secret_key = data[CONF_API_SECRET_KEY]
    api_auth_key = data[CONF_API_AUTH_KEY]

    uri = f"ws://{host}:{DEFAULT_PORT}"

    try:
        async with websockets.connect(uri, close_timeout=5) as websocket:
            # Send AUTH frame
            auth_payload = {"type": "AUTH"}
            await websocket.send(json.dumps(auth_payload))

            # Receive challenge
            response = await asyncio.wait_for(websocket.recv(), timeout=10)
            auth_response = json.loads(response)

            if auth_response.get("type") != "ENCRYPTED":
                raise CannotConnect("Unexpected response from device")

            encrypted_data = auth_response.get("data")
            received_mac = auth_response.get("mac")

            if not encrypted_data or not received_mac:
                raise CannotConnect("Invalid response structure")

            # Validate MAC
            data_str = json.dumps(encrypted_data, separators=(",", ":"))
            key_bytes = bytes.fromhex(api_auth_key)
            calc_mac = hmac.new(
                key_bytes, data_str.encode("utf-8"), hashlib.sha256
            ).digest()
            calc_mac_b64 = b64encode(calc_mac).decode("utf-8")

            if calc_mac_b64 != received_mac:
                raise InvalidAuth("MAC verification failed - invalid API keys")

            # Decrypt challenge
            challenge = decrypt_frame(encrypted_data, api_secret_key)
            if not challenge or not challenge.get("challenge"):
                raise InvalidAuth("Failed to decrypt challenge - invalid API keys")

            # Successfully authenticated
            _LOGGER.debug("Successfully validated connection to Remootio at %s", host)

    except websockets.exceptions.WebSocketException as err:
        _LOGGER.debug("WebSocket error: %s", err)
        raise CannotConnect(f"WebSocket connection failed: {err}") from err
    except asyncio.TimeoutError as err:
        raise CannotConnect("Connection timed out") from err
    except InvalidAuth:
        raise
    except CannotConnect:
        raise
    except Exception as err:
        _LOGGER.debug("Unexpected error: %s", err)
        raise CannotConnect(f"Unexpected error: {err}") from err

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
            # Normalize host (strip whitespace, lowercase)
            user_input[CONF_HOST] = user_input[CONF_HOST].strip().lower()

            # Set unique ID based on host to prevent duplicates
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
