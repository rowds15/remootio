"""Remootio API Client — single source of truth for device communication."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from base64 import b64decode, b64encode

import websockets
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


def encrypt_frame(
    payload: dict, encryption_key: str, mac_key: str | None = None
) -> dict:
    """Encrypt a frame using AES-CBC with HMAC-SHA256 MAC."""
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


class RemootioAPI:
    """Remootio device API client.

    Handles WebSocket connection, authentication, encryption, and command
    execution.  Each call opens a fresh WebSocket — the Remootio hardware is a
    limited embedded system where persistent connections add complexity for
    marginal benefit.
    """

    def __init__(
        self,
        host: str,
        api_secret_key: str,
        api_auth_key: str,
        port: int = DEFAULT_PORT,
    ) -> None:
        """Initialize the API client."""
        self._host = host
        self._api_secret_key = api_secret_key
        self._api_auth_key = api_auth_key
        self._port = port

    @property
    def host(self) -> str:
        """Return the device host."""
        return self._host

    async def _async_authenticate(
        self, websocket
    ) -> tuple[str, int]:
        """Perform the auth handshake and return (session_key_hex, initial_action_id).

        Raises CannotConnect or InvalidAuth on failure.
        """
        auth_payload = {"type": "AUTH"}
        await websocket.send(json.dumps(auth_payload))
        _LOGGER.debug("Sent AUTH frame")

        response = await asyncio.wait_for(websocket.recv(), timeout=10)
        auth_response = json.loads(response)
        _LOGGER.debug("Received auth response type: %s", auth_response.get("type"))

        if auth_response.get("type") != "ENCRYPTED":
            raise CannotConnect("Unexpected response from device")

        encrypted_data = auth_response.get("data")
        received_mac = auth_response.get("mac")

        if not encrypted_data or not received_mac:
            raise CannotConnect("Invalid response structure")

        # Validate MAC
        data_str = json.dumps(encrypted_data, separators=(",", ":"))
        key_bytes = bytes.fromhex(self._api_auth_key)
        calc_mac = hmac.new(
            key_bytes, data_str.encode("utf-8"), hashlib.sha256
        ).digest()
        calc_mac_b64 = b64encode(calc_mac).decode("utf-8")

        if calc_mac_b64 != received_mac:
            raise InvalidAuth("MAC verification failed - invalid API keys")

        _LOGGER.debug("MAC Verification SUCCESS for Auth Response")

        # Decrypt challenge
        challenge = decrypt_frame(encrypted_data, self._api_secret_key)
        if not challenge or not isinstance(challenge.get("challenge"), dict):
            raise InvalidAuth("Failed to decrypt challenge - invalid API keys")

        challenge_data = challenge["challenge"]
        if "sessionKey" not in challenge_data:
            raise InvalidAuth("Missing sessionKey in challenge response")

        session_key_b64 = challenge_data["sessionKey"]
        session_key_hex = b64decode(session_key_b64).hex()
        initial_action_id = challenge_data.get("initialActionId", 0)

        return session_key_hex, initial_action_id

    async def async_send_command(
        self, command_type: str, relay_number: int
    ) -> dict | None:
        """Open WS, authenticate, send command, return decrypted response dict.

        Returns the decrypted response payload, or None on communication failure.
        """
        uri = f"ws://{self._host}:{self._port}"

        try:
            async with websockets.connect(uri) as websocket:
                session_key_hex, initial_action_id = await self._async_authenticate(
                    websocket
                )
                action_id = (initial_action_id + 1) % 0x7FFFFFFF

                # Remootio API uses separate action types per output.
                # relay 1 → TRIGGER / QUERY; relay 2 → TRIGGER_SECONDARY (no QUERY variant).
                api_action_type = (
                    "TRIGGER_SECONDARY"
                    if relay_number == 2 and command_type == "TRIGGER"
                    else command_type
                )

                command_payload = {
                    "action": {
                        "type": api_action_type,
                        "id": action_id,
                    }
                }

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
                    relay_number,
                    command_payload,
                )

                await websocket.send(json.dumps(encrypted_message))
                _LOGGER.debug(
                    "Sent %s command (relay %d)", api_action_type, relay_number
                )

                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                result = json.loads(response)
                _LOGGER.debug("Command response: %s", result)

                if result.get("type") == "ENCRYPTED":
                    encrypted_data = result.get("data", result)
                    decrypted_result = decrypt_frame(encrypted_data, session_key_hex)
                    _LOGGER.debug("Command result: %s", decrypted_result)
                    return decrypted_result

                return None

        except (CannotConnect, InvalidAuth):
            raise
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout communicating with Remootio at %s", self._host)
            return None
        except Exception as err:
            _LOGGER.error("Error sending command: %s", err, exc_info=True)
            return None

    async def async_validate_connection(self) -> bool:
        """Open WS, authenticate only (no command). Used by config_flow.

        Raises CannotConnect or InvalidAuth on failure.
        Returns True on success.
        """
        uri = f"ws://{self._host}:{self._port}"

        try:
            async with websockets.connect(uri, close_timeout=5) as websocket:
                await self._async_authenticate(websocket)
                _LOGGER.debug(
                    "Successfully validated connection to Remootio at %s", self._host
                )
                return True
        except (CannotConnect, InvalidAuth):
            raise
        except websockets.exceptions.WebSocketException as err:
            _LOGGER.debug("WebSocket error: %s", err)
            raise CannotConnect(f"WebSocket connection failed: {err}") from err
        except asyncio.TimeoutError as err:
            raise CannotConnect("Connection timed out") from err
        except Exception as err:
            _LOGGER.debug("Unexpected error: %s", err)
            raise CannotConnect(f"Unexpected error: {err}") from err
