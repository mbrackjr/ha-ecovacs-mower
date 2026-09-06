"""Tests for mower identity and model-specific profiles."""

from unittest.mock import Mock

from custom_components.ecovacs_mower.deebot_patch.device import (
    A1600_AREA_MAPPING,
    DeviceIdentity,
    identity_for,
    profile_for,
    profile_for_class,
)


def test_identity_comes_from_the_deebot_device() -> None:
    device = Mock()
    device.device_info = {
        "class": "e4gqia",
        "deviceName": "GOAT A1600 LiDAR Pro",
    }
    device.fw_version = "1.11.31"

    assert identity_for(device) == DeviceIdentity(
        device_class="e4gqia",
        model="GOAT A1600 LiDAR Pro",
        firmware="1.11.31",
    )


def test_profile_is_selected_by_device_class() -> None:
    profile = profile_for_class("e4gqia")
    assert profile is not None
    assert profile.area_parameters is True
    assert profile.area_mapping is A1600_AREA_MAPPING

    other = profile_for_class("xmp9ds")
    assert other is not None
    assert other.area_parameters is False


def test_profile_for_device_uses_the_device_identity() -> None:
    device = Mock()
    device.device_info = {"class": "e4gqia"}
    assert profile_for(device) is profile_for_class("e4gqia")
