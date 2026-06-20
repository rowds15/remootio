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

class _ConfigEntry:
    def __init__(self, *, entry_id="test_entry", data=None):
        self.entry_id = entry_id
        self.data = data or {}

_make_module("homeassistant.config_entries", {
    "ConfigEntry": _ConfigEntry,
    "ConfigFlow": type("ConfigFlow", (), {
        "__init_subclass__": classmethod(lambda cls, **kw: None),
    }),
    "ConfigFlowResult": dict,
})

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

# --- voluptuous stub (used by config_flow) ---
class _VolSchema:
    def __init__(self, schema):
        self._schema = schema

class _Vol:
    Schema = _VolSchema
    @staticmethod
    def Required(key, **kwargs):
        return key
    @staticmethod
    def Optional(key, **kwargs):
        return key

_make_module("voluptuous", {
    "Schema": _VolSchema,
    "Required": _Vol.Required,
    "Optional": _Vol.Optional,
})

# --- sensor platform ---
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

# --- cover platform ---
class _CoverDeviceClass:
    GARAGE = "garage"

class _CoverEntityFeature:
    OPEN = 1
    CLOSE = 2

class _CoverEntity:
    _attr_has_entity_name = False
    _attr_unique_id = None
    _attr_name = None
    _attr_device_class = None
    _attr_supported_features = None

_make_module("homeassistant.components.cover", {
    "CoverDeviceClass": _CoverDeviceClass,
    "CoverEntity": _CoverEntity,
    "CoverEntityFeature": _CoverEntityFeature,
})

# --- button platform ---
class _ButtonEntity:
    _attr_has_entity_name = False
    _attr_unique_id = None
    _attr_name = None
    _attr_icon = None

_make_module("homeassistant.components.button", {"ButtonEntity": _ButtonEntity})

# --- helpers ---
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

class _CoordinatorEntity:
    """Stub for CoordinatorEntity — stores coordinator reference."""
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def __class_getitem__(cls, item):
        return cls

class _DataUpdateCoordinator:
    def __init__(self, hass, logger, *, name, update_interval):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data = None
        self.last_update_success = True

    def __class_getitem__(cls, item):
        return cls

    async def async_request_refresh(self):
        await self._async_update_data()

    async def async_config_entry_first_refresh(self):
        self.data = await self._async_update_data()

    def async_set_updated_data(self, data) -> None:
        self.data = data
        self.last_update_success = True
        self.async_update_listeners()

    def async_update_listeners(self) -> None:
        pass

_make_module("homeassistant.helpers.update_coordinator", {
    "DataUpdateCoordinator": _DataUpdateCoordinator,
    "CoordinatorEntity": _CoordinatorEntity,
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
