"""Remootio Cover Platform with encryption support."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from base64 import b64decode, b64encode
from datetime import timedelta

import websockets
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_API_AUTH_KEY,
    CONF_API_SECRET_KEY,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    SIGNAL_REMOOTIO_STATE_CHANGED,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Remootio covers from a config entry."""
    host = entry.data[CONF_HOST]
    api_secret_key = entry.data[CONF_API_SECRET_KEY]
    api_auth_key = entry.data[CONF_API_AUTH_KEY]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    # Create covers for both channels
    covers = [
        RemootioCover(
            hass=hass,
            name=name,
            host=host,
            api_secret_key=api_secret_key,
            api_auth_key=api_auth_key,
            entry_id=entry.entry_id,
            relay_number=1,
        ),
        RemootioCover(
            hass=hass,
            name=name,
            host=host,
            api_secret_key=api_secret_key,
            api_auth_key=api_auth_key,
            entry_id=entry.entry_id,
            relay_number=2,
        ),
    ]
    async_add_entities(covers, True)


def encrypt_frame(
    payload: dict, encryption_key: str, mac_key: str | None = None
) -> dict:
    """Encrypt a frame using AES-CBC."""
    encryption_key_bytes = bytes.fromhex(encryption_key)
    mac_key_bytes = bytes.fromhex(mac_key if mac_key else encryption_key)

    iv = secrets.token_bytes(16)

    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    padding_length = 16 - (len(payload_bytes) % 16)
    padded_payload = payload_bytes + bytes([padding_length] * padding_length)

    cipher = Cipher(
        algorithms.AES(encryption_key_bytes), modes.CBC(iv), backend=default_backend()
    )
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_payload) + encryptor.finalize()

    iv_b64 = b64encode(iv).decode("utf-8")
    payload_b64 = b64encode(ciphertext).decode("utf-8")

    data_obj = {"iv": iv_b64, "payload": payload_b64}

    data_str = json.dumps(data_obj, separators=(",", ":"))
    mac = hmac.new(mac_key_bytes, data_str.encode("utf-8"), hashlib.sha256).digest()

    return {"iv": iv_b64, "payload": payload_b64, "mac": b64encode(mac).decode("utf-8")}


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
        _LOGGER.error("Decryption error: %s", err)
        return None


class RemootioCover(CoverEntity):
    """Representation of a Remootio cover."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.GARAGE
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        host: str,
        api_secret_key: str,
        api_auth_key: str,
        entry_id: str,
        relay_number: int = 1,
    ) -> None:
        """Initialize the cover."""
        self.hass = hass
        self._device_name = name
        self._host = host
        self._api_secret_key = api_secret_key
        self._api_auth_key = api_auth_key
        self._entry_id = entry_id
        self._relay_number = relay_number
        self._state: str | None = None
        self._available = False
        self._attr_unique_id = f"remootio_{host.replace('.', '_')}_ch{relay_number}"
        self._attr_name = f"Channel {relay_number}"
        self._session_key: str | None = None
        self._action_id = 0

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for device registry."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._host)},
            name=self._device_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        if self._state is None:
            return None
        return self._state == "closed"

    @property
    def is_open(self) -> bool | None:
        """Return if the cover is open."""
        if self._state is None:
            return None
        return self._state == "open"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._available

    @property
    def relay_number(self) -> int:
        """Return the relay number for this cover."""
        return self._relay_number

    async def _send_command(self, command_type: str) -> bool:
        """Send a command to Remootio."""
        try:
            uri = f"ws://{self._host}:{DEFAULT_PORT}"

            async with websockets.connect(uri) as websocket:
                auth_payload = {"type": "AUTH"}

                await websocket.send(json.dumps(auth_payload))
                _LOGGER.debug("Sent AUTH frame")

                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                auth_response = json.loads(response)
                _LOGGER.debug("Received auth response type: %s", auth_response.get("type"))

                if auth_response.get("type") == "ENCRYPTED":
                    encrypted_data = auth_response.get("data")
                    received_mac = auth_response.get("mac")

                    if encrypted_data and received_mac:
                        data_str = json.dumps(encrypted_data, separators=(",", ":"))
                        key_bytes = bytes.fromhex(self._api_auth_key)
                        calc_mac = hmac.new(
                            key_bytes, data_str.encode("utf-8"), hashlib.sha256
                        ).digest()
                        calc_mac_b64 = b64encode(calc_mac).decode("utf-8")

                        if calc_mac_b64 != received_mac:
                            _LOGGER.error(
                                "MAC Verification FAILED. Calc: %s, Recv: %s",
                                calc_mac_b64,
                                received_mac,
                            )
                        else:
                            _LOGGER.debug("MAC Verification SUCCESS for Auth Response")

                    challenge = decrypt_frame(encrypted_data, self._api_secret_key)
                    _LOGGER.debug("Decrypted challenge: %s", challenge)

                    if challenge and challenge.get("challenge"):
                        session_key_b64 = challenge["challenge"].get("sessionKey")
                        self._session_key = session_key_b64
                        initial_action_id = challenge["challenge"].get(
                            "initialActionId", 0
                        )
                        self._action_id = (initial_action_id + 1) % 0x7FFFFFFF

                        # Include relayNumber in the command payload
                        command_payload = {
                            "action": {
                                "type": command_type,
                                "id": self._action_id,
                                "relayNumber": self._relay_number,
                            }
                        }

                        session_key_bytes = b64decode(session_key_b64)
                        session_key_hex = session_key_bytes.hex()

                        encrypted_command = encrypt_frame(
                            command_payload, session_key_hex, self._api_auth_key
                        )
                        encrypted_message = {
                            "type": "ENCRYPTED",
                            "data": {
                                "iv": encrypted_command["iv"],
                                "payload": encrypted_command["payload"],
                            },
                            "mac": encrypted_command["mac"],
                        }

                        _LOGGER.debug(
                            "Command payload for relay %d: %s",
                            self._relay_number,
                            command_payload,
                        )

                        await websocket.send(json.dumps(encrypted_message))
                        _LOGGER.debug(
                            "Sent %s command to relay %d",
                            command_type,
                            self._relay_number,
                        )

                        response = await asyncio.wait_for(websocket.recv(), timeout=5)
                        result = json.loads(response)
                        _LOGGER.debug("Command response: %s", result)

                        if result.get("type") == "ENCRYPTED":
                            encrypted_data = result.get("data", result)
                            decrypted_result = decrypt_frame(
                                encrypted_data, session_key_hex
                            )
                            _LOGGER.debug("Command result: %s", decrypted_result)

                            if decrypted_result and decrypted_result.get("response"):
                                state = decrypted_result["response"].get("state")
                                if state:
                                    old_state = self._state
                                    self._state = state
                                    self._available = True
                                    if old_state is not None and old_state != state:
                                        signal = f"{SIGNAL_REMOOTIO_STATE_CHANGED}_{self._host}_ch{self._relay_number}"
                                        async_dispatcher_send(
                                            self.hass, signal, old_state, state
                                        )

                        return True

                return False

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout communicating with Remootio")
            self._available = False
            return False
        except Exception as err:
            _LOGGER.error("Error sending command: %s", err, exc_info=True)
            self._available = False
            return False

    async def async_open_cover(self, **kwargs) -> None:
        """Open the cover."""
        await self._send_command("TRIGGER")

    async def async_close_cover(self, **kwargs) -> None:
        """Close the cover."""
        await self._send_command("TRIGGER")

    async def async_update(self) -> None:
        """Update the cover state."""
        await self._send_command("QUERY")
