"""Tests for the writable per-area mowing parameter number entities."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from tests import requires_ha

pytestmark = requires_ha


def _device() -> MagicMock:
    device = MagicMock()
    device.device_info = {"did": "did", "name": "name", "class": "e4gqia"}
    device.capabilities = MagicMock()
    device.events = MagicMock()
    return device


def _mapping():
    from custom_components.ecovacs_mower.area_sensors import AREA_PARAMETER_MAPPINGS

    return AREA_PARAMETER_MAPPINGS["e4gqia"]


def _full_area(area_id: str = "12"):
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerArea

    return MowerArea(
        area_id, mow_height_level=7, cut_mode=4, obstacle_height=15, angle=90
    )


def _seed_area(device: MagicMock, area) -> None:
    """Seed the authoritative area snapshot ``area_for`` reads.

    ``area_for``/``_areas_for`` are ``deebot_patch.areas`` internals; tests
    reach into them directly because nothing public populates this state
    outside of a real ``getAreaParameter``/``getAreaSet`` exchange.
    """
    from custom_components.ecovacs_mower.deebot_patch import areas

    areas._areas_for(device.events)[area.area_id] = area


def _cutting_height_description():
    from custom_components.ecovacs_mower.area_sensors import area_sensor_descriptions

    return area_sensor_descriptions("12", area_mapping=_mapping())[0]


def _mowing_speed_description():
    from custom_components.ecovacs_mower.area_sensors import area_sensor_descriptions

    return area_sensor_descriptions("12", area_mapping=_mapping())[1]


def test_build_set_area_parameter_refuses_an_incomplete_snapshot() -> None:
    from custom_components.ecovacs_mower.area_sensors import build_set_area_parameter

    incomplete = {
        "mow_height_level": 7,
        "cut_mode": None,
        "obstacle_height": 15,
        "angle": 90,
    }
    assert build_set_area_parameter("12", incomplete, "mow_height_level", 6) is None


def test_build_set_area_parameter_merges_the_other_three_values() -> None:
    from custom_components.ecovacs_mower.area_sensors import build_set_area_parameter

    current = {
        "mow_height_level": 7,
        "cut_mode": 4,
        "obstacle_height": 15,
        "angle": 90,
    }
    command = build_set_area_parameter("12", current, "cut_mode", 2)
    assert command._args["mowHeightLevel"] == 7
    assert command._args["cutMode"] == 2
    assert command._args["obstacleHeight"] == 15
    assert command._args["angle"] == 90


async def test_write_raises_when_the_area_has_not_reported_yet() -> None:
    from custom_components.ecovacs_mower.area_sensors import (
        EcovacsAreaNumber,
        _PendingAreaWrite,
    )
    from homeassistant.exceptions import HomeAssistantError

    device = _device()
    entity = EcovacsAreaNumber(
        device, "12", _cutting_height_description(), "North lawn", _PendingAreaWrite()
    )
    entity._execute_command = AsyncMock()

    try:
        await entity.async_set_native_value(7)
        raise AssertionError("expected HomeAssistantError")
    except HomeAssistantError:
        pass
    entity._execute_command.assert_not_called()


async def test_write_raises_for_an_unrepresentable_value() -> None:
    from custom_components.ecovacs_mower.area_sensors import (
        EcovacsAreaNumber,
        _PendingAreaWrite,
    )
    from homeassistant.exceptions import HomeAssistantError

    device = _device()
    _seed_area(device, _full_area())
    entity = EcovacsAreaNumber(
        device, "12", _cutting_height_description(), "North lawn", _PendingAreaWrite()
    )
    entity._execute_command = AsyncMock()

    try:
        # 12cm is not one of the seven validated A1600 heights.
        await entity.async_set_native_value(12)
        raise AssertionError("expected HomeAssistantError")
    except HomeAssistantError:
        pass
    entity._execute_command.assert_not_called()


async def test_a_successful_write_sends_one_complete_command_and_refreshes() -> None:
    from custom_components.ecovacs_mower.area_sensors import (
        EcovacsAreaNumber,
        _PendingAreaWrite,
    )

    device = _device()
    _seed_area(device, _full_area())
    entity = EcovacsAreaNumber(
        device, "12", _cutting_height_description(), "North lawn", _PendingAreaWrite()
    )
    entity._execute_command = AsyncMock()

    await entity.async_set_native_value(6)

    entity._execute_command.assert_called_once()
    command = entity._execute_command.call_args[0][0]
    assert command._args["mowHeightLevel"] == 4  # raw value for 6cm
    assert command._args["cutMode"] == 4
    device.events.request_refresh.assert_called_once()


async def test_a_sequential_second_write_merges_the_pending_values() -> None:
    """A second write, issued only after the first has returned, merges
    against the first write's sent values rather than the pre-write
    snapshot.

    This covers ordering correctness, not concurrency safety: two
    sequential ``await``s never overlap, since asyncio only switches
    coroutines at a suspension point and there is not one between this
    test's two calls. See ``test_concurrent_writes_do_not_revert_each_other``
    for the case that actually exercises the race Nord- identified in
    review — this test would pass even without the fix that closes it.
    """
    from custom_components.ecovacs_mower.area_sensors import (
        EcovacsAreaNumber,
        _PendingAreaWrite,
    )

    device = _device()
    _seed_area(device, _full_area())
    pending = _PendingAreaWrite()
    height_entity = EcovacsAreaNumber(
        device, "12", _cutting_height_description(), "North lawn", pending
    )
    speed_entity = EcovacsAreaNumber(
        device, "12", _mowing_speed_description(), "North lawn", pending
    )
    height_entity._execute_command = AsyncMock()
    speed_entity._execute_command = AsyncMock()

    # The authoritative snapshot is deliberately left unchanged here to
    # simulate the mower's confirmation not having arrived yet.
    await height_entity.async_set_native_value(6)
    await speed_entity.async_set_native_value(0.55)

    second_command = speed_entity._execute_command.call_args[0][0]
    assert second_command._args["mowHeightLevel"] == 4  # 6cm from the first write
    assert second_command._args["cutMode"] == 4  # 0.55 m/s


async def test_concurrent_writes_do_not_revert_each_other() -> None:
    """Regression test for the concurrent-write race Nord- identified in
    review (PR #97): recording the pending write *after* awaiting
    confirmation, rather than before, meant two writes dispatched at the
    same time — not just in quick sequence — could both read the same
    stale snapshot and the second would still revert the first.

    Home Assistant dispatches each ``number.set_value`` call as its own
    asyncio task (two automations firing together, a script's parallel
    block, or two targets in one service call), so this uses
    ``asyncio.create_task`` rather than sequential ``await``s. A naive test
    using sequential awaits cannot expose this: asyncio only switches
    coroutines at a suspension point, and there is not one between two
    sequential ``await`` statements — the first call fully completes,
    including everything after its own internal await, before the second
    one is even entered. That is exactly why the earlier, sequential
    version of this test passed against the buggy code and proved nothing
    about concurrency (see
    ``test_a_sequential_second_write_merges_the_pending_values``).

    Both writes are deliberately blocked inside ``_execute_command`` — the
    mocked mower "hangs" mid-request — until both have reached that point.
    That is the actual vulnerable window: after a write has computed its
    merged command but before the mower has confirmed it. Only once both
    tasks are confirmed to be sitting in that window are they released,
    so the test does not depend on any particular number of event-loop
    iterations or asyncio scheduling internals to force the interleaving.
    """
    from custom_components.ecovacs_mower.area_sensors import (
        EcovacsAreaNumber,
        _PendingAreaWrite,
    )

    device = _device()
    _seed_area(device, _full_area())
    pending = _PendingAreaWrite()
    height_entity = EcovacsAreaNumber(
        device, "12", _cutting_height_description(), "North lawn", pending
    )
    speed_entity = EcovacsAreaNumber(
        device, "12", _mowing_speed_description(), "North lawn", pending
    )

    release = asyncio.Event()
    dispatched = 0
    both_dispatched = asyncio.Event()

    async def blocking_execute(_command: object) -> None:
        nonlocal dispatched
        dispatched += 1
        if dispatched == 2:
            both_dispatched.set()
        await release.wait()

    height_entity._execute_command = AsyncMock(side_effect=blocking_execute)
    speed_entity._execute_command = AsyncMock(side_effect=blocking_execute)

    task1 = asyncio.create_task(height_entity.async_set_native_value(6))
    task2 = asyncio.create_task(speed_entity.async_set_native_value(0.55))

    # Wait until both writes have computed their command and are blocked on
    # confirmation — the exact window the fix must stay correct through.
    await asyncio.wait_for(both_dispatched.wait(), timeout=1)
    release.set()
    await task1
    await task2

    second_command = speed_entity._execute_command.call_args[0][0]
    assert second_command._args["mowHeightLevel"] == 4  # 6cm from the first write
    assert second_command._args["cutMode"] == 4  # 0.55 m/s


async def test_a_fresh_snapshot_clears_a_pending_write() -> None:
    from custom_components.ecovacs_mower.area_sensors import _setup_device_area_sensors
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerAreaEvent

    device = _device()
    config_entry = MagicMock()
    config_entry.async_on_unload = MagicMock()
    add_entities = MagicMock()

    _setup_device_area_sensors(device, config_entry, add_entities, _mapping())
    on_area_state = device.events.subscribe.call_args[0][1]
    area = _full_area()

    await on_area_state(MowerAreaEvent((area,)))
    entities = add_entities.call_args[0][0]
    for entity in entities:
        entity.async_write_ha_state = MagicMock()
    height_entity = next(
        e for e in entities if e.entity_description.raw_field == "mow_height_level"
    )
    height_entity._pending.raw_values = {"mow_height_level": 2}

    await on_area_state(MowerAreaEvent((area,)))

    assert height_entity._pending.raw_values is None


async def test_a_removed_area_becomes_unavailable_and_recovers() -> None:
    from custom_components.ecovacs_mower.area_sensors import _setup_device_area_sensors
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerAreaEvent

    device = _device()
    config_entry = MagicMock()
    config_entry.async_on_unload = MagicMock()
    add_entities = MagicMock()

    _setup_device_area_sensors(device, config_entry, add_entities, _mapping())
    on_area_state = device.events.subscribe.call_args[0][1]

    area = _full_area()
    await on_area_state(MowerAreaEvent((area,)))
    entities = add_entities.call_args[0][0]
    for entity in entities:
        entity.async_write_ha_state = MagicMock()

    await on_area_state(MowerAreaEvent(()))
    assert all(not e.available for e in entities)
    assert all(e.native_value is None for e in entities)

    await on_area_state(MowerAreaEvent((area,)))
    assert all(e.available for e in entities)
