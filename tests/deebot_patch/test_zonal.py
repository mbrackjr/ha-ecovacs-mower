"""Tests for the GOAT zone-mowing command."""

import pytest
from deebot_client.commands.json.clean import Clean, CleanV2
from deebot_client.hardware import _DEVICES, get_static_device_info

from custom_components.ecovacs_mower.deebot_patch.hardware import patch_device_info
from custom_components.ecovacs_mower.deebot_patch.zonal import (
    MowArea,
    _ZoneCleanNonV2,
    _ZoneCleanV2,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Empty the library cache between tests."""
    yield
    _DEVICES.pop("e4gqia", None)


def test_zone_commands_are_clean_commands() -> None:
    assert issubclass(_ZoneCleanNonV2, Clean)
    assert issubclass(_ZoneCleanV2, CleanV2)


def test_spot_area_payload_uses_saved_area_ids() -> None:
    command = _ZoneCleanNonV2([1, 2, 3])
    assert command.NAME == "clean"
    assert command._args == {
        "act": "start",
        "content": {"type": "spotArea", "value": "1,2,3"},
    }


def test_v2_spot_area_payload_has_the_same_nested_shape() -> None:
    command = _ZoneCleanV2([7])
    assert command.NAME == "clean_V2"
    assert command._args == {
        "act": "start",
        "content": {"type": "spotArea", "value": "7"},
    }


def test_mow_area_requires_spot_area_mode() -> None:
    with pytest.raises(ValueError, match="Unsupported mower area mode"):
        MowArea("auto", [1])


def test_mow_area_requires_an_area() -> None:
    with pytest.raises(ValueError, match="At least one area ID"):
        MowArea("spotArea", [])


def test_mow_area_rejects_multiple_cleanings() -> None:
    with pytest.raises(ValueError, match="exactly one cleaning pass"):
        MowArea("spotArea", [1], 2)


def test_mow_area_equality_includes_area_ids() -> None:
    assert MowArea("spotArea", [1, 3]) == MowArea("spotArea", [1, 3])
    assert MowArea("spotArea", [1, 3]) != MowArea("spotArea", [1, 2])


async def test_patch_exposes_the_area_command() -> None:
    await patch_device_info("e4gqia")
    info = await get_static_device_info("e4gqia")
    assert info.capabilities.clean.action.area is MowArea
