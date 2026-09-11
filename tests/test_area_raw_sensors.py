"""Tests for raw per-area diagnostic sensors."""

from unittest.mock import MagicMock

from custom_components.ecovacs_mower.area_sensors import (
    EcovacsAreaRawSensor,
    area_raw_sensor_descriptions,
)
from custom_components.ecovacs_mower.deebot_patch.areas import MowerArea, MowerAreaEvent


def _device() -> MagicMock:
    device = MagicMock()
    device.device_info = {"did": "did", "name": "name", "class": "e4gqia"}
    device.fw_version = "1.0"
    device.mac = None
    device.capabilities = MagicMock()
    device.events = MagicMock()
    return device


def test_raw_area_sensor_descriptions_keep_numeric_area_identity() -> None:
    descriptions = area_raw_sensor_descriptions("12")
    assert [d.key for d in descriptions] == [
        "area_12_raw_mow_height_level", "area_12_raw_cut_mode",
        "area_12_raw_obstacle_height", "area_12_raw_angle",
    ]
    assert [d.suggested_object_id for d in descriptions] == [
        "12_raw_mow_height_level", "12_raw_cut_mode",
        "12_raw_obstacle_height", "12_raw_angle",
    ]
    assert all(d.entity_category.value == "diagnostic" for d in descriptions)
    assert all(d.native_unit_of_measurement is None for d in descriptions)


async def test_raw_area_sensor_projects_exact_raw_values_and_name() -> None:
    device = _device()
    entity = EcovacsAreaRawSensor(device, "12", area_raw_sensor_descriptions("12")[1], "Old name")
    entity.async_write_ha_state = MagicMock()
    entity.hass = None
    await entity._on_area_state(MowerAreaEvent((MowerArea(
        "12", name="North lawn", mow_height_level=7, cut_mode=4,
        obstacle_height=15, angle=123,
    ),)))
    assert entity.native_value == 4
    assert entity.name == "North lawn - Raw cut mode"
    entity.async_write_ha_state.assert_called_once()


async def test_raw_area_sensor_becomes_unknown_when_area_is_missing() -> None:
    device = _device()
    entity = EcovacsAreaRawSensor(device, "12", area_raw_sensor_descriptions("12")[0], "North lawn")
    entity.async_write_ha_state = MagicMock()
    entity.hass = None
    await entity._on_area_state(MowerAreaEvent((MowerArea("13", mow_height_level=9),)))
    assert entity.native_value is None
    entity.async_write_ha_state.assert_called_once()
