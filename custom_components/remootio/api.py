"""Remootio API Client — single source of truth for device communication."""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import secrets
from base64 import b64decode, b64encode
from collections.abc import Awaitable, Callable

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


def build_encrypted_message(
    payload: dict, session_key_hex: str, auth_key: str
) -> str:
    """Encrypt *payload* and wrap it in the ENCRYPTED frame the device expects."""
    encrypted = encrypt_frame(payload, session_key_hex, auth_key)
    return json.dumps(
        {
            "type": "ENCRYPTED",
            "data": {"iv": encrypted["iv"], "payload": encrypted["payload"]},
            "mac": encrypted["mac"],
        }
    )


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


class RemootioEventListener:
    """Persistent WebSocket listener that delivers real-time StateChange events.

    Maintains an authenticated connection and calls *on_state_change* whenever
    a StateChange event arrives.  Reconnects automatically with exponential
    backoff.  Tracks event counters across reconnections to skip replayed
    events from the device's 100-event buffer.

    The Remootio device does not answer WebSocket protocol-level ping frames,
    so ``ping_interval`` is disabled (enabling it makes the ``websockets``
    library declare a perfectly healthy connection dead every ping_timeout
    seconds).  Instead the listener sends the device's own application-level
    ``PING`` frame periodically to keep the session alive, and a watchdog
    force-closes the connection if nothing at all — not even a reply — has
    been heard for too long, so a silently-dropped TCP connection (e.g. a
    Wi-Fi blip) can't block the read loop forever.  On every (re)connect the
    listener sends a QUERY so state changes that happened while disconnected
    are picked up immediately.
    """

    _BACKOFF_INITIAL = 5
    _BACKOFF_MAX = 60
    _PING_INTERVAL = 45
    _ACTIVITY_TIMEOUT = 90
    _IO_TIMEOUT = 10

    def __init__(
        self,
        api: RemootioAPI,
        on_state_change: Callable[[str], Awaitable[None]],
    ) -> None:
        self._api = api
        self._on_state_change = on_state_change
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._last_event_cnt: int = -1
        self._connected = False
        self._last_activity: float = 0.0

    @property
    def connected(self) -> bool:
        """Return True while the listener holds an authenticated connection."""
        return self._connected

    @property
    def seconds_idle(self) -> float:
        """Return seconds since the last inbound frame from the device.

        The coordinator uses this alongside ``connected`` — a connection can
        go half-open (the local socket accepts writes but the peer is gone)
        without ``connected`` ever flipping False, so callers that need to
        know whether the listener is *actually* live, not just nominally
        connected, should check this too.
        """
        return asyncio.get_running_loop().time() - self._last_activity

    async def async_start(self) -> None:
        """Start the background listener task."""
        self._stop_event.clear()
        self._task = asyncio.ensure_future(self._listen_loop())

    async def async_stop(self) -> None:
        """Stop the background listener task and wait for it to exit."""
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _listen_loop(self) -> None:
        """Reconnect loop with exponential backoff."""
        backoff = self._BACKOFF_INITIAL
        while not self._stop_event.is_set():
            try:
                await self._connect_and_listen()
                backoff = self._BACKOFF_INITIAL
            except asyncio.CancelledError:
                return
            except Exception as err:
                _LOGGER.warning(
                    "Remootio event listener error (%s): %s — retrying in %ss",
                    self._api.host,
                    err,
                    backoff,
                )

            if self._stop_event.is_set():
                return
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                return
            except asyncio.TimeoutError:
                backoff = min(backoff * 2, self._BACKOFF_MAX)

    async def _connect_and_listen(self) -> None:
        """Authenticate then consume events until the connection drops."""
        uri = f"ws://{self._api._host}:{self._api._port}"
        async with websockets.connect(uri, ping_interval=None) as websocket:
            session_key_hex, initial_action_id = await self._api._async_authenticate(
                websocket
            )
            _LOGGER.debug("Event listener authenticated to %s", self._api.host)

            # Query current state so changes that happened while the listener
            # was disconnected (e.g. during a TRIGGER command) are not missed.
            query_payload = {
                "action": {
                    "type": "QUERY",
                    "id": (initial_action_id + 1) % 0x7FFFFFFF,
                }
            }
            # No watchdog is running yet at this point (it starts below),
            # so this send has nothing else bounding it — a half-open
            # connection here would wedge the reconnect loop before it even
            # gets a chance to run one.
            await asyncio.wait_for(
                websocket.send(
                    build_encrypted_message(
                        query_payload, session_key_hex, self._api._api_auth_key
                    )
                ),
                timeout=self._IO_TIMEOUT,
            )

            loop = asyncio.get_running_loop()
            self._last_activity = loop.time()
            watchdog_task = asyncio.ensure_future(self._keepalive_watchdog(websocket))
            self._connected = True
            try:
                async for raw in websocket:
                    self._last_activity = loop.time()
                    frame = json.loads(raw)
                    if frame.get("type") != "ENCRYPTED":
                        continue

                    decrypted = decrypt_frame(frame.get("data", frame), session_key_hex)
                    if not decrypted:
                        continue

                    response = decrypted.get("response")
                    if response is not None:
                        state = response.get("state")
                        if state and state != "no sensor":
                            await self._on_state_change(state)
                        continue

                    event = decrypted.get("event", {})
                    if event.get("type") != "StateChange":
                        continue

                    state = event.get("state")
                    if not state or state == "no sensor":
                        continue

                    cnt = event.get("cnt", -1)
                    # Skip replayed events; large backward jump means device restarted.
                    if cnt <= self._last_event_cnt and (self._last_event_cnt - cnt) < 50:
                        continue

                    self._last_event_cnt = cnt
                    await self._on_state_change(state)
            finally:
                self._connected = False
                watchdog_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watchdog_task

    async def _keepalive_watchdog(self, websocket) -> None:
        """Send application-level PINGs and force-close a silently-dead connection.

        The device doesn't answer protocol-level WebSocket pings, so this is
        the only way to detect a connection that has died without a clean
        TCP close (e.g. the network dropped out from under it).  Any inbound
        traffic — including the device's own PONG reply — resets the
        activity clock via ``_connect_and_listen``'s read loop.
        """
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(self._PING_INTERVAL)
            idle = loop.time() - self._last_activity
            if idle >= self._ACTIVITY_TIMEOUT:
                _LOGGER.warning(
                    "No response from Remootio at %s for %.0fs — closing stale connection",
                    self._api.host,
                    idle,
                )
                await self._force_close(websocket)
                return
            try:
                await asyncio.wait_for(
                    websocket.send(json.dumps({"type": "PING"})),
                    timeout=self._IO_TIMEOUT,
                )
            except Exception:
                # Failed OR stuck PING send means the connection is broken —
                # force it closed so the read loop unblocks and the
                # reconnect loop takes over.
                await self._force_close(websocket)
                return

    async def _force_close(self, websocket) -> None:
        """Guarantee the connection actually terminates.

        A half-open TCP connection — the local socket keeps accepting writes
        into its send buffer even though nothing ever reaches or comes back
        from the peer — can make a graceful ``close()`` hang exactly the way
        ``send()`` does, since closing writes a frame too and waits for the
        peer's reply.  Bound it with the same timeout as PING, and if even
        that doesn't return in time, abort the transport directly — a local,
        synchronous operation that can't block on the network — rather than
        leave the watchdog (and the read loop it exists to unblock) stuck
        forever.
        """
        try:
            await asyncio.wait_for(websocket.close(), timeout=self._IO_TIMEOUT)
        except Exception:
            transport = getattr(websocket, "transport", None)
            if transport is not None:
                with contextlib.suppress(Exception):
                    transport.abort()


class RemootioAPI:
    """Remootio device API client.

    Handles WebSocket connection, authentication, encryption, and command
    execution.  Each call opens a fresh WebSocket — the Remootio hardware is a
    limited embedded system where persistent connections add complexity for
    marginal benefit.
    """

    # Bounds for every send/recv in the auth and command exchange. A bare
    # ``send()`` can hang as easily as ``recv()`` on a half-open TCP
    # connection (the local socket accepts the write; nothing ever reaches
    # or comes back from the peer), so both directions get the same timeout
    # around each step — see RemootioEventListener for the same pattern.
    _AUTH_TIMEOUT = 10
    _COMMAND_TIMEOUT = 5

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
        await asyncio.wait_for(
            websocket.send(json.dumps(auth_payload)), timeout=self._AUTH_TIMEOUT
        )
        _LOGGER.debug("Sent AUTH frame")

        response = await asyncio.wait_for(websocket.recv(), timeout=self._AUTH_TIMEOUT)
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

                _LOGGER.debug(
                    "Command payload for relay %d: %s",
                    relay_number,
                    command_payload,
                )

                await asyncio.wait_for(
                    websocket.send(
                        build_encrypted_message(
                            command_payload, session_key_hex, self._api_auth_key
                        )
                    ),
                    timeout=self._COMMAND_TIMEOUT,
                )
                _LOGGER.debug(
                    "Sent %s command (relay %d)", api_action_type, relay_number
                )

                response = await asyncio.wait_for(
                    websocket.recv(), timeout=self._COMMAND_TIMEOUT
                )
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
