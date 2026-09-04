"""Tests for the GOAT area parameter service."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.ecovacs_mower.deebot_patch.areas import (
    A1600_PROFILE,
    MowerArea,
)
from custom_components.ecovacs_mower import services


@pytest.mark.parametrize(
    ("height", "wire"),
    [(3.0, 7), (6.0, 4), (9.0, 1)],
)
def test_a1600_mow_height_round_trip(height: float, wire: int) -> None:
    """A1600 cutting heights map to the expected wire levels."""
    assert A1600_PROFILE.mow_height_to_wire(height) == wire
    assert A1600_PROFILE.mow_height_from_wire(wire) == height


@pytest.mark.parametrize(
    ("speed", "wire"),
    [(0.40, 7), (0.55, 4), (0.70, 1)],
)
def test_a1600_speed_round_trip(speed: float, wire: int) -> None:
    """A1600 mowing speeds map to cutMode and back."""
    assert A1600_PROFILE.speed_to_wire(speed) == wire
    assert A1600_PROFILE.speed_from_wire(wire) == speed


@pytest.mark.parametrize("height, wire", [(10, 1), (15, 2), (20, 3)])
def test_a1600_obstacle_height_round_trip(height: int, wire: int) -> None:
    """A1600 obstacle thresholds map to obstacleHeight and back."""
    assert A1600_PROFILE.obstacle_height_to_wire(height) == wire
    assert A1600_PROFILE.obstacle_height_from_wire(wire) == height


def test_a1600_angle_round_trip() -> None:
    """A1600 cutting angles use the app/wire coordinate conversion."""
    for degrees in (0, 56, 89, 180, 359):
        wire = A1600_PROFILE.angle_to_wire(degrees)
        assert A1600_PROFILE.angle_from_wire(wire) == degrees


def test_a1600_profiles_reject_unsupported_values() -> None:
    """The service mapping rejects values the mower does not support."""
    with pytest.raises(ValueError):
        A1600_PROFILE.mow_height_to_wire(3.5)
    with pytest.raises(ValueError):
        A1600_PROFILE.speed_to_wire(0.43)
    with pytest.raises(KeyError):
        A1600_PROFILE.obstacle_height_to_wire(12)
    with pytest.raises(ValueError):
        A1600_PROFILE.angle_to_wire(360)


@pytest.mark.asyncio
async def test_set_area_parameters_sends_all_fields_and_keeps_omitted_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The write contains all five fields, using current values for omissions."""
    device = Mock()
    device.device_info = {"class": "e4gqia", "did": "did"}
    device.events = Mock()
    device.execute_command = AsyncMock(
        side_effect=[
            {"ret": "ok", "resp": {"body": {"code": 0}}},
            {"ret": "ok", "resp": {"body": {"code": 0}}},
        ]
    )
    current = MowerArea(
        area_id="2",
        mow_height_level=4,
        cut_mode=5,
        obstacle_height=2,
        angle=214,
    )
    monkeypatch.setattr(services, "_find_device", Mock(return_value=device))
    monkeypatch.setattr(services, "get_area", Mock(return_value=current))
    monkeypatch.setattr(services.asyncio, "sleep", AsyncMock())

    call = Mock()
    call.data = {
        "device_id": "ha-device",
        "area_id": 2,
        "speed_mps": "0.60",
    }
    hass = Mock()
    monkeypatch.setattr(services, "async_extract_device_ids", Mock(return_value={"ha-device"}))

    await services.async_set_area_parameters(hass, call)

    set_command = device.execute_command.await_args_list[0].args[0]
    assert set_command._args == {
        "areaID": "2",
        "mowHeightLevel": 4,
        "cutMode": 3,
        "obstacleHeight": 2,
        "angle": 214,
    }
    assert device.execute_command.await_count == 2


@pytest.mark.asyncio
async def test_set_area_parameters_rejects_unsupported_mower(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only user-validated mower classes may use the write service."""
    device = Mock()
    device.device_info = {"class": "not-validated", "did": "did"}
    monkeypatch.setattr(services, "_find_device", Mock(return_value=device))
    monkeypatch.setattr(services, "async_extract_device_ids", Mock(return_value={"ha-device"}))

    call = Mock()
    call.data = {"device_id": "ha-device", "area_id": 1, "mow_height_cm": "6.0"}

    with pytest.raises(Exception, match="not validated"):
        await services.async_set_area_parameters(Mock(), call)
