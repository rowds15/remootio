"""Remootio Cover Platform with encryption support."""
import asyncio
import json
import logging
import secrets
import hmac
import hashlib
from datetime import timedelta
from base64 import b64encode, b64decode

import websockets
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from homeassistant.components.cover import (
    CoverEntity,
    CoverDeviceClass,
    CoverEntityFeature,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

CONF_API_SECRET_KEY = "api_secret_key"
CONF_API_AUTH_KEY = "api_auth_key"

SCAN_INTERVAL = timedelta(seconds=30)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Remootio cover platform."""
    host = config.get(CONF_HOST)
    api_secret_key = config.get(CONF_API_SECRET_KEY)
    api_auth_key = config.get(CONF_API_AUTH_KEY)
    name = config.get("name", "Garage Door")

    cover = RemootioCover(hass, name, host, api_secret_key, api_auth_key)
    async_add_entities([cover], True)


def encrypt_frame(payload, encryption_key, mac_key=None):
    """Encrypt a frame using AES-CBC."""
    # Convert hex keys to bytes
    encryption_key_bytes = bytes.fromhex(encryption_key)
    mac_key_bytes = bytes.fromhex(mac_key if mac_key else encryption_key)

    # Generate random IV
    iv = secrets.token_bytes(16)

    # Convert payload to bytes (Compact JSON)
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')

    # Pad payload to multiple of 16 bytes (PKCS7 padding)
    padding_length = 16 - (len(payload_bytes) % 16)
    padded_payload = payload_bytes + bytes([padding_length] * padding_length)

    # Encrypt
    cipher = Cipher(algorithms.AES(encryption_key_bytes),
                   modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_payload) + encryptor.finalize()

    # Prepare data field
    iv_b64 = b64encode(iv).decode('utf-8')
    payload_b64 = b64encode(ciphertext).decode('utf-8')
    
    data_obj = {
        "iv": iv_b64,
        "payload": payload_b64
    }

    # MAC over the JSON string of the data object (Compact JSON)
    data_str = json.dumps(data_obj, separators=(',', ':'))
    mac = hmac.new(mac_key_bytes, data_str.encode('utf-8'), hashlib.sha256).digest()

    return {
        "iv": iv_b64,
        "payload": payload_b64,
        "mac": b64encode(mac).decode('utf-8')
    }


def decrypt_frame(encrypted_frame, key):
    """Decrypt a frame using AES-CBC."""
    try:
        # Convert hex key to bytes
        key_bytes = bytes.fromhex(key)

        iv = b64decode(encrypted_frame["iv"])
        ciphertext = b64decode(encrypted_frame["payload"])

        # Decrypt
        cipher = Cipher(algorithms.AES(key_bytes),
                       modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        # Remove PKCS7 padding
        padding_length = padded_plaintext[-1]
        plaintext = padded_plaintext[:-padding_length]

        return json.loads(plaintext.decode('utf-8'))
    except Exception as e:
        _LOGGER.error(f"Decryption error: {e}")
        return None


class RemootioCover(CoverEntity):
    """Representation of a Remootio cover."""

    def __init__(self, hass, name, host, api_secret_key, api_auth_key):
        """Initialize the cover."""
        self.hass = hass
        self._name = name
        self._host = host
        self._api_secret_key = api_secret_key
        self._api_auth_key = api_auth_key
        self._state = None
        self._available = False
        self._attr_unique_id = f"remootio_{host.replace('.', '_')}"
        self._session_key = None
        self._action_id = 0

    @property
    def name(self):
        """Return the name of the cover."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._attr_unique_id

    @property
    def is_closed(self):
        """Return if the cover is closed."""
        return self._state == "closed"

    @property
    def is_open(self):
        """Return if the cover is open."""
        return self._state == "open"

    @property
    def available(self):
        """Return if entity is available."""
        return self._available

    @property
    def device_class(self):
        """Return the device class."""
        return CoverDeviceClass.GARAGE

    @property
    def supported_features(self):
        """Flag supported features."""
        return CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    async def _send_command(self, command_type):
        """Send a command to Remootio."""
        try:
            uri = f"ws://{self._host}:8080"

            async with websockets.connect(uri) as websocket:
                # Step 1: Send AUTH frame
                auth_payload = {
                    "type": "AUTH"
                }

                await websocket.send(json.dumps(auth_payload))
                _LOGGER.debug("Sent AUTH frame")

                # Step 2: Receive challenge
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                auth_response = json.loads(response)
                _LOGGER.info(f"Received auth response type: {auth_response.get('type')}")
                _LOGGER.info(f"Full auth response: {auth_response}")

                if auth_response.get("type") == "ENCRYPTED":
                    # Validate MAC of Auth Response (Test Logic)
                    encrypted_data = auth_response.get("data")
                    received_mac = auth_response.get("mac")
                    
                    if encrypted_data and received_mac:
                         # Reconstruct data string
                         data_str = json.dumps(encrypted_data, separators=(',', ':'))
                         key_bytes = bytes.fromhex(self._api_auth_key)
                         calc_mac = hmac.new(key_bytes, data_str.encode('utf-8'), hashlib.sha256).digest()
                         calc_mac_b64 = b64encode(calc_mac).decode('utf-8')
                         
                         if calc_mac_b64 != received_mac:
                             _LOGGER.error(f"MAC Verification FAILED. Calc: {calc_mac_b64}, Recv: {received_mac}")
                             # We continue anyway to see if session works, but this is a red flag.
                         else:
                             _LOGGER.info("MAC Verification SUCCESS for Auth Response")

                    # Decrypt challenge using API SECRET KEY (not auth key!)
                    _LOGGER.info(f"Encrypted data structure: {encrypted_data}")
                    challenge = decrypt_frame(encrypted_data, self._api_secret_key)
                    _LOGGER.info(f"Decrypted challenge: {challenge}")

                    if challenge and challenge.get("challenge"):
                        # Extract session key and action ID
                        session_key_b64 = challenge["challenge"].get("sessionKey")
                        self._session_key = session_key_b64  # Store base64 version
                        initial_action_id = challenge["challenge"].get("initialActionId", 0)
                        # First action ID must be initialActionId + 1
                        self._action_id = (initial_action_id + 1) % 0x7FFFFFFF

                        # Step 3: Send command (encrypted with session key!)
                        command_payload = {
                            "action": {
                                "type": command_type,
                                "id": self._action_id
                            }
                        }

                        # Decode session key from base64 to hex for encryption
                        session_key_bytes = b64decode(session_key_b64)
                        session_key_hex = session_key_bytes.hex()

                        # Encrypt with session key, MAC with API Auth Key
                        encrypted_command = encrypt_frame(
                            command_payload,
                            session_key_hex,
                            self._api_auth_key # Back to API Auth Key
                        )
                        encrypted_message = {
                            "type": "ENCRYPTED",
                            "data": {
                                "iv": encrypted_command["iv"],
                                "payload": encrypted_command["payload"]
                            },
                            "mac": encrypted_command["mac"]
                        }

                        _LOGGER.info(f"Command payload: {command_payload}")
                        _LOGGER.info(f"Encrypted command data: {encrypted_command}")
                        _LOGGER.info(f"Full message: {encrypted_message}")

                        await websocket.send(json.dumps(encrypted_message))
                        _LOGGER.debug(f"Sent {command_type} command")

                        # Receive response
                        response = await asyncio.wait_for(websocket.recv(), timeout=5)
                        result = json.loads(response)
                        _LOGGER.debug(f"Command response: {result}")

                        if result.get("type") == "ENCRYPTED":
                            encrypted_data = result.get("data", result)
                            decrypted_result = decrypt_frame(encrypted_data, session_key_hex)
                            _LOGGER.info(f"Command result: {decrypted_result}")

                            # Update state from response
                            if decrypted_result and decrypted_result.get("response"):
                                state = decrypted_result["response"].get("state")
                                if state:
                                    self._state = state
                                    self._available = True

                        return True

                return False

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout communicating with Remootio")
            self._available = False
            return False
        except Exception as err:
            _LOGGER.error(f"Error sending command: {err}", exc_info=True)
            self._available = False
            return False

    async def async_open_cover(self, **kwargs):
        """Open the cover."""
        await self._send_command("TRIGGER")

    async def async_close_cover(self, **kwargs):
        """Close the cover."""
        await self._send_command("TRIGGER")

    async def async_update(self):
        """Update the cover state."""
        await self._send_command("QUERY")
