"""Tests for the model-gated area capability."""

import pytest
from deebot_client.hardware import _DEVICES, get_static_device_info

from custom_components.ecovacs_mower.deebot_patch.areas import (
    GetAreaParameter,
    GetAreaSet,
    MowerAreaEvent,
)
from custom_components.ecovacs_mower.deebot_patch.hardware import (
    SUPPORTED_CLASSES,
    patch_device_info,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Keep the library device cache isolated between tests."""
    for class_ in SUPPORTED_CLASSES:
        _DEVICES.pop(class_, None)
    yield
    for class_ in SUPPORTED_CLASSES:
        _DEVICES.pop(class_, None)


async def test_a1600_area_capability_has_both_active_reads() -> None:
    """The HA-facing area event owns the two protocol refresh operations."""
    await patch_device_info("e4gqia")
    info = await get_static_device_info("e4gqia")
    assert info is not None
    commands = info.capabilities.get_refresh_commands(MowerAreaEvent)
    assert [type(command) for command in commands] == [GetAreaParameter, GetAreaSet]


@pytest.mark.parametrize(
    "class_", ("2i0fns", "9bts2s", "2px96q", "77atlz", "xmp9ds")
)
async def test_other_supported_mowers_do_not_get_a1600_area_capability(
    class_: str,
) -> None:
    """A1600-specific area semantics must not leak to other mower classes."""
    await patch_device_info(class_)
    info = await get_static_device_info(class_)
    assert info is not None
    assert info.capabilities.get_refresh_commands(MowerAreaEvent) == []
