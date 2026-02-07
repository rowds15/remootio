"""Shared fixtures for Remootio integration tests."""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub out homeassistant imports so tests run without a full HA install.
# We only need the modules that our code actually imports at the top level.
# ---------------------------------------------------------------------------

_STUBS: dict[str, ModuleType] = {}


def _make_module(name: str, attrs: dict | None = None) -> ModuleType:
    mod = ModuleType(name)
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    _STUBS[name] = mod
    return mod


# --- homeassistant core stubs ---
_make_module("homeassistant")
_make_module("homeassistant.core", {
    "HomeAssistant": MagicMock,
    "callback": lambda fn: fn,
})
_make_module("homeassistant.config_entries", {"ConfigEntry": MagicMock})
class _Platform:
    COVER = "cover"
    BUTTON = "button"
    SENSOR = "sensor"

_make_module("homeassistant.const", {
    "CONF_HOST": "host",
    "CONF_NAME": "name",
    "Platform": _Platform,
})
_make_module("homeassistant.exceptions")

# sensor platform
class _SensorDeviceClass:
    TIMESTAMP = "timestamp"

class _SensorStateClass:
    TOTAL_INCREASING = "total_increasing"

class _SensorEntity:
    _attr_has_entity_name = False
    _attr_unique_id = None
    _attr_name = None
    _attr_icon = None
    _attr_device_class = None
    _attr_state_class = None
    hass = None

    async def async_added_to_hass(self) -> None:
        pass

    def async_on_remove(self, unsub):
        pass

    def async_write_ha_state(self):
        pass

_make_module("homeassistant.components")
_make_module("homeassistant.components.sensor", {
    "SensorDeviceClass": _SensorDeviceClass,
    "SensorEntity": _SensorEntity,
    "SensorStateClass": _SensorStateClass,
})

# helpers
_make_module("homeassistant.helpers")

class _DeviceInfo(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for k, v in kwargs.items():
            setattr(self, k, v)

_make_module("homeassistant.helpers.device_registry", {"DeviceInfo": _DeviceInfo})

_dispatcher_connections: list = []

def _async_dispatcher_connect(hass, signal, handler):
    _dispatcher_connections.append((signal, handler))
    return lambda: None

def _async_dispatcher_send(hass, signal, *args):
    pass

_make_module("homeassistant.helpers.dispatcher", {
    "async_dispatcher_connect": _async_dispatcher_connect,
    "async_dispatcher_send": _async_dispatcher_send,
})

_make_module("homeassistant.helpers.entity_platform", {"AddEntitiesCallback": MagicMock})

class _RestoreEntity:
    async def async_added_to_hass(self) -> None:
        pass

    async def async_get_last_state(self):
        return None

_make_module("homeassistant.helpers.restore_state", {"RestoreEntity": _RestoreEntity})

class _UpdateFailed(Exception):
    pass

class _DataUpdateCoordinator:
    def __init__(self, hass, logger, *, name, update_interval):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data = None

    def __class_getitem__(cls, item):
        return cls

    async def async_request_refresh(self):
        await self._async_update_data()

_make_module("homeassistant.helpers.update_coordinator", {
    "DataUpdateCoordinator": _DataUpdateCoordinator,
    "UpdateFailed": _UpdateFailed,
})

import datetime as _dt

class _dt_util:
    @staticmethod
    def utcnow():
        return _dt.datetime.now(_dt.timezone.utc)

_make_module("homeassistant.util", {})
_make_module("homeassistant.util.dt", {"utcnow": _dt_util.utcnow})

# Install all stubs before any remootio imports
sys.modules.update(_STUBS)

# ---------------------------------------------------------------------------
# Now we can safely import the integration code
# ---------------------------------------------------------------------------
from custom_components.remootio.api import RemootioAPI  # noqa: E402
from custom_components.remootio.coordinator import RemootioCoordinator  # noqa: E402

TEST_HOST = "192.168.1.100"
TEST_SECRET_KEY = "a" * 64  # 32-byte hex key
TEST_AUTH_KEY = "b" * 64


@pytest.fixture
def mock_hass():
    """Return a minimal mock HomeAssistant instance."""
    hass = MagicMock()
    hass.data = {}
    return hass


@pytest.fixture
def mock_api():
    """Return an AsyncMock RemootioAPI."""
    api = AsyncMock(spec=RemootioAPI)
    api.host = TEST_HOST
    api._host = TEST_HOST
    api._api_secret_key = TEST_SECRET_KEY
    api._api_auth_key = TEST_AUTH_KEY
    api._port = 8080
    return api


@pytest.fixture
def mock_coordinator(mock_hass, mock_api):
    """Return a real RemootioCoordinator with mocked dependencies."""
    coordinator = RemootioCoordinator(mock_hass, mock_api, "Test Garage")
    coordinator._previous_states = {1: None, 2: None}
    return coordinator


def make_query_response(state: str) -> dict:
    """Build a QUERY response dict as returned by the API."""
    return {"response": {"state": state}}
