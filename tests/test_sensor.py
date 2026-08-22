"""Tests for custom_components.remootio.sensor."""
from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.remootio.sensor import (
    RemootioLastClosedSensor,
    RemootioLastOpenedSensor,
    RemootioOperationCountSensor,
)
from tests.conftest import TEST_HOST


def _make_coordinator():
    """Build a minimal mock coordinator for sensor tests."""
    coordinator = MagicMock()
    coordinator.host = TEST_HOST
    coordinator.device_info = {
        "identifiers": {("remootio", TEST_HOST)},
        "name": "Test Garage",
    }
    return coordinator


# ── Operation Count Sensor ─────────────────────────────────────────────────

class TestOperationCountSensor:

    def test_operation_count_increments_on_open(self):
        """Count increases when new_state is 'open'."""
        sensor = RemootioOperationCountSensor(_make_coordinator(), 1)
        assert sensor.native_value == 0

        sensor._handle_state_changed("closed", "open")
        assert sensor.native_value == 1

        sensor._handle_state_changed("closed", "open")
        assert sensor.native_value == 2

    def test_operation_count_ignores_closed(self):
        """Count stays at 0 when new_state is 'closed'."""
        sensor = RemootioOperationCountSensor(_make_coordinator(), 1)
        sensor._handle_state_changed("open", "closed")
        assert sensor.native_value == 0


# ── Last Opened Sensor ────────────────────────────────────────────────────

class TestLastOpenedSensor:

    def test_last_opened_records_timestamp(self):
        """native_value becomes a datetime when door opens."""
        sensor = RemootioLastOpenedSensor(_make_coordinator(), 1)
        assert sensor.native_value is None

        sensor._handle_state_changed("closed", "open")

        assert isinstance(sensor.native_value, datetime.datetime)
        assert sensor.native_value.tzinfo is not None

    def test_last_opened_ignores_closed(self):
        """Timestamp stays None when new_state is 'closed'."""
        sensor = RemootioLastOpenedSensor(_make_coordinator(), 1)
        sensor._handle_state_changed("open", "closed")
        assert sensor.native_value is None


# ── Last Closed Sensor ────────────────────────────────────────────────────

class TestLastClosedSensor:

    def test_last_closed_records_timestamp(self):
        """native_value becomes a datetime when door closes."""
        sensor = RemootioLastClosedSensor(_make_coordinator(), 1)
        assert sensor.native_value is None

        sensor._handle_state_changed("open", "closed")

        assert isinstance(sensor.native_value, datetime.datetime)
        assert sensor.native_value.tzinfo is not None

    def test_last_closed_ignores_open(self):
        """Timestamp stays None when new_state is 'open'."""
        sensor = RemootioLastClosedSensor(_make_coordinator(), 2)
        sensor._handle_state_changed("closed", "open")
        assert sensor.native_value is None


# ── Unique IDs ────────────────────────────────────────────────────────────

class TestUniqueIds:

    def test_unique_ids(self):
        """All 6 sensor unique IDs follow the expected pattern."""
        coordinator = _make_coordinator()
        host_safe = TEST_HOST.replace(".", "_")

        expected = {
            f"remootio_{host_safe}_operation_count_ch1",
            f"remootio_{host_safe}_operation_count_ch2",
            f"remootio_{host_safe}_last_opened_ch1",
            f"remootio_{host_safe}_last_opened_ch2",
            f"remootio_{host_safe}_last_closed_ch1",
            f"remootio_{host_safe}_last_closed_ch2",
        }

        actual = set()
        for relay in (1, 2):
            actual.add(RemootioOperationCountSensor(coordinator, relay)._attr_unique_id)
            actual.add(RemootioLastOpenedSensor(coordinator, relay)._attr_unique_id)
            actual.add(RemootioLastClosedSensor(coordinator, relay)._attr_unique_id)

        assert actual == expected

    def test_translation_keys(self):
        """All 6 sensor translation keys follow the expected pattern."""
        coordinator = _make_coordinator()

        expected = {
            "operation_count_channel_1",
            "operation_count_channel_2",
            "last_opened_channel_1",
            "last_opened_channel_2",
            "last_closed_channel_1",
            "last_closed_channel_2",
        }

        actual = set()
        for relay in (1, 2):
            actual.add(RemootioOperationCountSensor(coordinator, relay)._attr_translation_key)
            actual.add(RemootioLastOpenedSensor(coordinator, relay)._attr_translation_key)
            actual.add(RemootioLastClosedSensor(coordinator, relay)._attr_translation_key)

        assert actual == expected


# ── device_info delegation ────────────────────────────────────────────────

class TestDeviceInfoDelegation:

    def test_device_info_delegates(self):
        """All sensor types delegate device_info to the coordinator."""
        coordinator = _make_coordinator()
        sensors = [
            RemootioOperationCountSensor(coordinator, 1),
            RemootioLastOpenedSensor(coordinator, 1),
            RemootioLastClosedSensor(coordinator, 1),
        ]
        for sensor in sensors:
            assert sensor.device_info is coordinator.device_info


# ── Availability ──────────────────────────────────────────────────────────

class TestAvailability:
    """Sensors must go unavailable with the coordinator.

    These sensors derive their value from dispatcher signals, not
    coordinator.data, so nothing else would flip them unavailable during an
    outage — see RemootioCoordinator._MAX_CONSECUTIVE_FAILURES.
    """

    def test_available_when_coordinator_healthy(self):
        coordinator = _make_coordinator()
        coordinator.last_update_success = True
        sensor = RemootioOperationCountSensor(coordinator, 1)
        assert sensor.available is True

    def test_unavailable_when_coordinator_failed(self):
        coordinator = _make_coordinator()
        coordinator.last_update_success = False
        sensor = RemootioOperationCountSensor(coordinator, 1)
        assert sensor.available is False
