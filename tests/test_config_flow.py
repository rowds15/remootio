"""Tests for custom_components.remootio.config_flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.remootio.api import CannotConnect, InvalidAuth
from custom_components.remootio.config_flow import RemootioConfigFlow, validate_input


CONF_HOST = "host"
CONF_API_SECRET_KEY = "api_secret_key"
CONF_API_AUTH_KEY = "api_auth_key"
CONF_NAME = "name"


def _valid_input(**overrides):
    """Return a valid user input dict."""
    data = {
        CONF_HOST: "192.168.1.100",
        CONF_API_SECRET_KEY: "secret",
        CONF_API_AUTH_KEY: "auth",
    }
    data.update(overrides)
    return data


class TestValidateInput:

    @pytest.mark.asyncio
    async def test_validate_input_success(self):
        with patch("custom_components.remootio.config_flow.RemootioAPI") as mock_cls:
            mock_cls.return_value.async_validate_connection = AsyncMock()
            result = await validate_input(_valid_input(**{CONF_NAME: "My Garage"}))

        assert result == {"title": "My Garage"}
        mock_cls.assert_called_once_with(
            host="192.168.1.100",
            api_secret_key="secret",
            api_auth_key="auth",
        )

    @pytest.mark.asyncio
    async def test_validate_input_cannot_connect(self):
        with patch("custom_components.remootio.config_flow.RemootioAPI") as mock_cls:
            mock_cls.return_value.async_validate_connection = AsyncMock(
                side_effect=CannotConnect
            )
            with pytest.raises(CannotConnect):
                await validate_input(_valid_input())

    @pytest.mark.asyncio
    async def test_validate_input_invalid_auth(self):
        with patch("custom_components.remootio.config_flow.RemootioAPI") as mock_cls:
            mock_cls.return_value.async_validate_connection = AsyncMock(
                side_effect=InvalidAuth
            )
            with pytest.raises(InvalidAuth):
                await validate_input(_valid_input())


class TestAsyncStepUser:

    def _make_flow(self):
        flow = RemootioConfigFlow()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(
            return_value={"type": "create_entry", "title": "Test", "data": {}}
        )
        flow.async_show_form = MagicMock(
            return_value={"type": "form", "step_id": "user", "errors": {}}
        )
        return flow

    @pytest.mark.asyncio
    async def test_step_user_no_input_shows_form(self):
        flow = self._make_flow()
        result = await flow.async_step_user(None)
        assert result["type"] == "form"
        flow.async_show_form.assert_called_once()

    @pytest.mark.asyncio
    async def test_step_user_success(self):
        flow = self._make_flow()
        user_input = _valid_input()
        with patch(
            "custom_components.remootio.config_flow.validate_input",
            return_value={"title": "Test"},
        ):
            result = await flow.async_step_user(user_input)

        assert result["type"] == "create_entry"
        flow.async_create_entry.assert_called_once_with(title="Test", data=user_input)

    @pytest.mark.asyncio
    async def test_step_user_cannot_connect(self):
        flow = self._make_flow()
        with patch(
            "custom_components.remootio.config_flow.validate_input",
            side_effect=CannotConnect,
        ):
            await flow.async_step_user(_valid_input())

        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"] == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_step_user_invalid_auth(self):
        flow = self._make_flow()
        with patch(
            "custom_components.remootio.config_flow.validate_input",
            side_effect=InvalidAuth,
        ):
            await flow.async_step_user(_valid_input())

        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"] == {"base": "invalid_auth"}

    @pytest.mark.asyncio
    async def test_step_user_normalizes_host(self):
        flow = self._make_flow()
        user_input = _valid_input(**{CONF_HOST: "  192.168.1.100  "})
        with patch(
            "custom_components.remootio.config_flow.validate_input",
            return_value={"title": "Test"},
        ):
            await flow.async_step_user(user_input)

        flow.async_set_unique_id.assert_called_with("192.168.1.100")
        call_kwargs = flow.async_create_entry.call_args[1]
        assert call_kwargs["data"][CONF_HOST] == "192.168.1.100"
