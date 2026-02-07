"""Tests for custom_components.remootio.api."""
from __future__ import annotations

import asyncio
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
