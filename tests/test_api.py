"""Tests for custom_components.remootio.api."""
from __future__ import annotations

import asyncio
import contextlib
import json
from base64 import b64decode, b64encode
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.remootio.api import (
    CannotConnect,
    InvalidAuth,
    RemootioAPI,
    decrypt_frame,
    encrypt_frame,
)
from tests.conftest import TEST_AUTH_KEY, TEST_HOST, TEST_SECRET_KEY


# ── encrypt / decrypt ──────────────────────────────────────────────────────

class TestEncryptDecrypt:
    """Round-trip and error tests for encrypt_frame / decrypt_frame."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypting then decrypting with the same key yields the original payload."""
        payload = {"action": {"type": "QUERY", "id": 1, "relayNumber": 1}}
        encrypted = encrypt_frame(payload, TEST_SECRET_KEY, TEST_AUTH_KEY)

        assert "iv" in encrypted
        assert "payload" in encrypted
        assert "mac" in encrypted

        decrypted = decrypt_frame(encrypted, TEST_SECRET_KEY)
        assert decrypted == payload

    def test_decrypt_invalid_key_returns_none(self):
        """Decrypting with the wrong key returns None."""
        payload = {"hello": "world"}
        encrypted = encrypt_frame(payload, TEST_SECRET_KEY, TEST_AUTH_KEY)
        wrong_key = "c" * 64
        assert decrypt_frame(encrypted, wrong_key) is None

    def test_decrypt_malformed_returns_none(self):
        """Malformed encrypted data returns None."""
        bad_frame = {"iv": "not-valid-base64!!!", "payload": "also-bad!!!"}
        assert decrypt_frame(bad_frame, TEST_SECRET_KEY) is None


# ── async_send_command ─────────────────────────────────────────────────────

class TestAsyncSendCommand:
    """Tests for RemootioAPI.async_send_command."""

    @pytest.mark.asyncio
    async def test_async_send_command_success(self):
        """Successful command returns decrypted response dict."""
        api = RemootioAPI(TEST_HOST, TEST_SECRET_KEY, TEST_AUTH_KEY)

        # Build a fake challenge response for authentication
        challenge_payload = {
            "challenge": {
                "sessionKey": b64encode(bytes.fromhex(TEST_SECRET_KEY)).decode(),
                "initialActionId": 100,
            }
        }
        encrypted_challenge = encrypt_frame(challenge_payload, TEST_SECRET_KEY, TEST_AUTH_KEY)
        auth_response = {
            "type": "ENCRYPTED",
            "data": {"iv": encrypted_challenge["iv"], "payload": encrypted_challenge["payload"]},
            "mac": encrypted_challenge["mac"],
        }

        # Build a fake command response
        command_result_payload = {"response": {"state": "open"}}
        session_key = TEST_SECRET_KEY  # we set sessionKey = TEST_SECRET_KEY above
        encrypted_cmd_response = encrypt_frame(command_result_payload, session_key, TEST_AUTH_KEY)
        cmd_response = {
            "type": "ENCRYPTED",
            "data": {
                "iv": encrypted_cmd_response["iv"],
                "payload": encrypted_cmd_response["payload"],
            },
            "mac": encrypted_cmd_response["mac"],
        }

        ws_mock = AsyncMock()
        ws_mock.recv = AsyncMock(side_effect=[
            json.dumps(auth_response),
            json.dumps(cmd_response),
        ])
        ws_mock.send = AsyncMock()

        mock_connect = AsyncMock()
        mock_connect.__aenter__ = AsyncMock(return_value=ws_mock)
        mock_connect.__aexit__ = AsyncMock(return_value=False)

        with patch("custom_components.remootio.api.websockets.connect", return_value=mock_connect):
            result = await api.async_send_command("QUERY", 1)

        assert result is not None
        assert result["response"]["state"] == "open"

    @pytest.mark.asyncio
    async def test_async_send_command_timeout(self):
        """Timeout during communication returns None."""
        api = RemootioAPI(TEST_HOST, TEST_SECRET_KEY, TEST_AUTH_KEY)

        mock_connect = AsyncMock()
        mock_connect.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_connect.__aexit__ = AsyncMock(return_value=False)

        with patch("custom_components.remootio.api.websockets.connect", return_value=mock_connect):
            result = await api.async_send_command("QUERY", 1)

        assert result is None


# ── async_validate_connection ──────────────────────────────────────────────

class TestAsyncValidateConnection:
    """Tests for RemootioAPI.async_validate_connection."""

    @pytest.mark.asyncio
    async def test_async_validate_connection_success(self):
        """Successful auth handshake returns True."""
        api = RemootioAPI(TEST_HOST, TEST_SECRET_KEY, TEST_AUTH_KEY)

        challenge_payload = {
            "challenge": {
                "sessionKey": b64encode(bytes.fromhex(TEST_SECRET_KEY)).decode(),
                "initialActionId": 100,
            }
        }
        encrypted_challenge = encrypt_frame(challenge_payload, TEST_SECRET_KEY, TEST_AUTH_KEY)
        auth_response = {
            "type": "ENCRYPTED",
            "data": {"iv": encrypted_challenge["iv"], "payload": encrypted_challenge["payload"]},
            "mac": encrypted_challenge["mac"],
        }

        ws_mock = AsyncMock()
        ws_mock.recv = AsyncMock(return_value=json.dumps(auth_response))
        ws_mock.send = AsyncMock()

        mock_connect = AsyncMock()
        mock_connect.__aenter__ = AsyncMock(return_value=ws_mock)
        mock_connect.__aexit__ = AsyncMock(return_value=False)

        with patch("custom_components.remootio.api.websockets.connect", return_value=mock_connect):
            result = await api.async_validate_connection()

        assert result is True

    @pytest.mark.asyncio
    async def test_async_validate_connection_invalid_auth(self):
        """Bad MAC in auth response raises InvalidAuth."""
        api = RemootioAPI(TEST_HOST, TEST_SECRET_KEY, TEST_AUTH_KEY)

        auth_response = {
            "type": "ENCRYPTED",
            "data": {"iv": b64encode(b"\x00" * 16).decode(), "payload": b64encode(b"\x00" * 16).decode()},
            "mac": b64encode(b"bad-mac-value-here!!12345678").decode(),
        }

        ws_mock = AsyncMock()
        ws_mock.recv = AsyncMock(return_value=json.dumps(auth_response))
        ws_mock.send = AsyncMock()

        mock_connect = AsyncMock()
        mock_connect.__aenter__ = AsyncMock(return_value=ws_mock)
        mock_connect.__aexit__ = AsyncMock(return_value=False)

        with patch("custom_components.remootio.api.websockets.connect", return_value=mock_connect):
            with pytest.raises(InvalidAuth):
                await api.async_validate_connection()

    @pytest.mark.asyncio
    async def test_async_validate_connection_ws_error(self):
        """WebSocketException during connection raises CannotConnect."""
        import websockets

        api = RemootioAPI(TEST_HOST, TEST_SECRET_KEY, TEST_AUTH_KEY)

        mock_connect = AsyncMock()
        mock_connect.__aenter__ = AsyncMock(
            side_effect=websockets.exceptions.WebSocketException("conn refused")
        )
        mock_connect.__aexit__ = AsyncMock(return_value=False)

        with patch("custom_components.remootio.api.websockets.connect", return_value=mock_connect):
            with pytest.raises(CannotConnect):
                await api.async_validate_connection()


# ── RemootioEventListener ──────────────────────────────────────────────────

class AsyncIterMock:
    """Async iterator mock for websocket message streams."""
    def __init__(self, items):
        self._items = iter(items)
    def __aiter__(self):
        return self
    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


class TestRemootioEventListener:
    """Tests for RemootioEventListener."""

    def _make_listener(self, callback=None):
        from custom_components.remootio.api import RemootioEventListener
        api = RemootioAPI(TEST_HOST, TEST_SECRET_KEY, TEST_AUTH_KEY)
        cb = callback or AsyncMock()
        return RemootioEventListener(api, cb), cb

    def _make_auth_response(self):
        """Build the encrypted auth challenge frame the device sends."""
        challenge_payload = {
            "challenge": {
                "sessionKey": b64encode(bytes.fromhex(TEST_SECRET_KEY)).decode(),
                "initialActionId": 0,
            }
        }
        enc = encrypt_frame(challenge_payload, TEST_SECRET_KEY, TEST_AUTH_KEY)
        return json.dumps({
            "type": "ENCRYPTED",
            "data": {"iv": enc["iv"], "payload": enc["payload"]},
            "mac": enc["mac"],
        })

    def _make_state_change_frame(self, state: str, cnt: int, session_key: str = TEST_SECRET_KEY):
        """Build an encrypted StateChange event frame."""
        event_payload = {"event": {"cnt": cnt, "type": "StateChange", "state": state, "t100ms": 1000}}
        enc = encrypt_frame(event_payload, session_key, TEST_AUTH_KEY)
        return json.dumps({
            "type": "ENCRYPTED",
            "data": {"iv": enc["iv"], "payload": enc["payload"]},
            "mac": enc["mac"],
        })

    def _make_ws_mock(self, frames):
        """Build a websocket mock that yields the given frames on async iteration."""
        ws_mock = AsyncMock()
        ws_mock.send = AsyncMock()
        ws_mock.recv = AsyncMock(return_value=self._make_auth_response())
        ws_mock.__aiter__ = MagicMock(return_value=AsyncIterMock(frames))
        return ws_mock

    def _make_connect_ctx(self, ws_mock):
        """Wrap ws_mock in an async context manager."""
        connect_ctx = MagicMock()
        connect_ctx.__aenter__ = AsyncMock(return_value=ws_mock)
        connect_ctx.__aexit__ = AsyncMock(return_value=False)
        return connect_ctx

    def _make_query_response_frame(self, state: str):
        """Build an encrypted QUERY response frame."""
        response_payload = {"response": {"type": "QUERY", "id": 1, "success": True, "state": state}}
        enc = encrypt_frame(response_payload, TEST_SECRET_KEY, TEST_AUTH_KEY)
        return json.dumps({
            "type": "ENCRYPTED",
            "data": {"iv": enc["iv"], "payload": enc["payload"]},
            "mac": enc["mac"],
        })

    @pytest.mark.asyncio
    async def test_sends_query_on_connect(self):
        """The listener sends an encrypted QUERY right after authenticating."""
        from custom_components.remootio.api import decrypt_frame
        listener, callback = self._make_listener()
        ws_mock = self._make_ws_mock([])

        with patch("custom_components.remootio.api.websockets.connect", return_value=self._make_connect_ctx(ws_mock)):
            await listener._connect_and_listen()

        # send[0] is the AUTH frame; send[1] is the handshake QUERY.
        sent = json.loads(ws_mock.send.await_args_list[1].args[0])
        assert sent["type"] == "ENCRYPTED"
        decrypted = decrypt_frame(sent["data"], TEST_SECRET_KEY)
        assert decrypted == {"action": {"type": "QUERY", "id": 1}}

    @pytest.mark.asyncio
    async def test_delivers_query_response_state(self):
        """A QUERY response frame delivers its state to the callback."""
        listener, callback = self._make_listener()
        ws_mock = self._make_ws_mock([self._make_query_response_frame("closed")])

        with patch("custom_components.remootio.api.websockets.connect", return_value=self._make_connect_ctx(ws_mock)):
            await listener._connect_and_listen()

        callback.assert_awaited_once_with("closed")

    @pytest.mark.asyncio
    async def test_ignores_no_sensor_query_response(self):
        """A QUERY response with 'no sensor' state is not delivered."""
        listener, callback = self._make_listener()
        ws_mock = self._make_ws_mock([self._make_query_response_frame("no sensor")])

        with patch("custom_components.remootio.api.websockets.connect", return_value=self._make_connect_ctx(ws_mock)):
            await listener._connect_and_listen()

        callback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_connected_flag_lifecycle(self):
        """connected is True while consuming events and False after disconnect."""
        listener, _ = self._make_listener()
        seen_connected = []

        async def _record(state):
            seen_connected.append(listener.connected)

        listener._on_state_change = _record
        ws_mock = self._make_ws_mock([self._make_state_change_frame("open", cnt=1)])

        assert listener.connected is False
        with patch("custom_components.remootio.api.websockets.connect", return_value=self._make_connect_ctx(ws_mock)):
            await listener._connect_and_listen()

        assert seen_connected == [True]
        assert listener.connected is False

    @pytest.mark.asyncio
    async def test_watchdog_sends_app_level_ping(self):
        """The watchdog sends Remootio PING frames while the connection is active."""
        listener, _ = self._make_listener()
        listener._PING_INTERVAL = 0
        listener._ACTIVITY_TIMEOUT = 9999
        listener._last_activity = asyncio.get_running_loop().time()
        ws_mock = AsyncMock()

        task = asyncio.ensure_future(listener._keepalive_watchdog(ws_mock))
        await asyncio.sleep(0.01)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        ws_mock.send.assert_awaited_with(json.dumps({"type": "PING"}))
        ws_mock.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_watchdog_closes_stale_connection(self):
        """No inbound traffic past the activity timeout closes the connection."""
        listener, _ = self._make_listener()
        listener._PING_INTERVAL = 0
        listener._ACTIVITY_TIMEOUT = 0
        listener._last_activity = 0.0
        ws_mock = AsyncMock()

        await listener._keepalive_watchdog(ws_mock)

        ws_mock.close.assert_awaited_once()
        ws_mock.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_watchdog_closes_connection_on_ping_send_failure(self):
        """A failed PING send closes the connection instead of leaking the error."""
        listener, _ = self._make_listener()
        listener._PING_INTERVAL = 0
        listener._ACTIVITY_TIMEOUT = 9999
        listener._last_activity = asyncio.get_running_loop().time()
        ws_mock = AsyncMock()
        ws_mock.send = AsyncMock(side_effect=OSError("broken pipe"))

        await listener._keepalive_watchdog(ws_mock)

        ws_mock.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delivers_state_change_event(self):
        """StateChange event calls the callback with the new state string."""
        listener, callback = self._make_listener()
        ws_mock = self._make_ws_mock([self._make_state_change_frame("open", cnt=1)])

        with patch("custom_components.remootio.api.websockets.connect", return_value=self._make_connect_ctx(ws_mock)):
            await listener._connect_and_listen()

        callback.assert_awaited_once_with("open")

    @pytest.mark.asyncio
    async def test_ignores_non_statechange_events(self):
        """Non-StateChange event types are silently ignored."""
        listener, callback = self._make_listener()
        relay_trigger_payload = {"event": {"cnt": 1, "type": "RelayTrigger", "state": "open", "t100ms": 1000}}
        enc = encrypt_frame(relay_trigger_payload, TEST_SECRET_KEY, TEST_AUTH_KEY)
        relay_frame = json.dumps({
            "type": "ENCRYPTED",
            "data": {"iv": enc["iv"], "payload": enc["payload"]},
            "mac": enc["mac"],
        })
        ws_mock = self._make_ws_mock([relay_frame])

        with patch("custom_components.remootio.api.websockets.connect", return_value=self._make_connect_ctx(ws_mock)):
            await listener._connect_and_listen()

        callback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ignores_no_sensor_state(self):
        """'no sensor' state events are not delivered to the callback."""
        listener, callback = self._make_listener()
        ws_mock = self._make_ws_mock([self._make_state_change_frame("no sensor", cnt=1)])

        with patch("custom_components.remootio.api.websockets.connect", return_value=self._make_connect_ctx(ws_mock)):
            await listener._connect_and_listen()

        callback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_already_seen_cnt(self):
        """Events with cnt <= last_seen_cnt are skipped (replay buffer dedup)."""
        listener, callback = self._make_listener()
        listener._last_event_cnt = 10

        frames = [
            self._make_state_change_frame("open", cnt=5),
            self._make_state_change_frame("closed", cnt=10),
            self._make_state_change_frame("open", cnt=11),
        ]
        ws_mock = self._make_ws_mock(frames)

        with patch("custom_components.remootio.api.websockets.connect", return_value=self._make_connect_ctx(ws_mock)):
            await listener._connect_and_listen()

        callback.assert_awaited_once_with("open")
        assert listener._last_event_cnt == 11

    @pytest.mark.asyncio
    async def test_processes_event_after_device_restart(self):
        """cnt gap > 50 below last_seen_cnt is treated as device restart — event is delivered."""
        listener, callback = self._make_listener()
        listener._last_event_cnt = 90

        ws_mock = self._make_ws_mock([self._make_state_change_frame("closed", cnt=1)])

        with patch("custom_components.remootio.api.websockets.connect", return_value=self._make_connect_ctx(ws_mock)):
            await listener._connect_and_listen()

        callback.assert_awaited_once_with("closed")

    @pytest.mark.asyncio
    async def test_async_stop_cancels_task(self):
        """async_stop cancels the running listener task."""
        listener, callback = self._make_listener()

        async def _forever():
            await asyncio.sleep(9999)

        listener._task = asyncio.ensure_future(_forever())
        await listener.async_stop()

        assert listener._task is None

    @pytest.mark.asyncio
    async def test_listen_loop_reconnects_on_error(self):
        """_listen_loop retries after _connect_and_listen raises, then stops."""
        listener, callback = self._make_listener()

        call_count = 0

        async def _fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OSError("connection refused")
            listener._stop_event.set()

        listener._connect_and_listen = _fail_twice
        listener._BACKOFF_INITIAL = 0

        await listener._listen_loop()

        assert call_count == 3
