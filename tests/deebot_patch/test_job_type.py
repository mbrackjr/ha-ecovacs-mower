"""Tests for the mower job-type events."""

from unittest.mock import AsyncMock, Mock

from deebot_client.event_bus import EventBus
from deebot_client.message import HandlingState

from custom_components.ecovacs_mower.deebot_patch.job_type import (
    MowerJobTypeEvent,
    OnMowScheduleStartType,
    OnMowSpotAreaStartType,
)


def _bus() -> EventBus:
    return EventBus(AsyncMock(), Mock(get_refresh_commands=lambda _event: []))


def test_spot_area_start_preserves_the_existing_handler_and_adds_job_type() -> None:
    bus = _bus()
    result = OnMowSpotAreaStartType._handle_body(bus, {"trigger": "app"})

    assert result.state is HandlingState.SUCCESS
    assert bus.get_last_event(MowerJobTypeEvent) == MowerJobTypeEvent("start", "spotarea")


def test_schedule_start_reports_a_different_job_type() -> None:
    bus = _bus()
    result = OnMowScheduleStartType._handle_body(bus, {"trigger": "schedule"})

    assert result.state is HandlingState.SUCCESS
    assert bus.get_last_event(MowerJobTypeEvent) == MowerJobTypeEvent("start", "schedule")


def test_missing_trigger_does_not_create_job_type_state() -> None:
    bus = _bus()
    result = OnMowSpotAreaStartType._handle_body(bus, {})

    assert result.state is HandlingState.ANALYSE
    assert bus.get_last_event(MowerJobTypeEvent) is None
