"""Track the GOAT job type reported by task bury-point messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from deebot_client.event_bus import EventBus
from deebot_client.events.base import Event
from deebot_client.message import HandlingResult, HandlingState

from .messages import (
    OnMowScheduleStart,
    OnMowScheduleStop,
    OnMowSpotAreaStart,
    OnMowSpotAreaStop,
)


@dataclass(frozen=True)
class MowerJobTypeEvent(Event):
    """The job type the mower says has started or stopped."""

    phase: str
    job_type: str


class _OnMowJobType:
    """Add job-type state while preserving the existing job-edge event."""

    PHASE: ClassVar[str]
    JOB_TYPE: ClassVar[str]

    @classmethod
    def _publish_job_type(
        cls, event_bus: EventBus, result: HandlingResult
    ) -> HandlingResult:
        """Publish the job type after the existing parser accepts the payload."""
        if result.state is HandlingState.SUCCESS:
            event_bus.notify(MowerJobTypeEvent(cls.PHASE, cls.JOB_TYPE))
        return result


class OnMowScheduleStartType(_OnMowJobType, OnMowScheduleStart):
    """A scheduled mowing job begins."""

    NAME = OnMowScheduleStart.NAME
    PHASE = "start"
    JOB_TYPE = "schedule"

    @classmethod
    def _handle_body(
        cls, event_bus: EventBus, body: dict[str, Any]
    ) -> HandlingResult:
        return cls._publish_job_type(event_bus, super()._handle_body(event_bus, body))


class OnMowScheduleStopType(_OnMowJobType, OnMowScheduleStop):
    """A scheduled mowing job ends."""

    NAME = OnMowScheduleStop.NAME
    PHASE = "stop"
    JOB_TYPE = "schedule"

    @classmethod
    def _handle_body(
        cls, event_bus: EventBus, body: dict[str, Any]
    ) -> HandlingResult:
        return cls._publish_job_type(event_bus, super()._handle_body(event_bus, body))


class OnMowSpotAreaStartType(_OnMowJobType, OnMowSpotAreaStart):
    """A spot-area mowing job begins."""

    NAME = OnMowSpotAreaStart.NAME
    PHASE = "start"
    JOB_TYPE = "spotarea"

    @classmethod
    def _handle_body(
        cls, event_bus: EventBus, body: dict[str, Any]
    ) -> HandlingResult:
        return cls._publish_job_type(event_bus, super()._handle_body(event_bus, body))


class OnMowSpotAreaStopType(_OnMowJobType, OnMowSpotAreaStop):
    """A spot-area mowing job ends."""

    NAME = OnMowSpotAreaStop.NAME
    PHASE = "stop"
    JOB_TYPE = "spotarea"

    @classmethod
    def _handle_body(
        cls, event_bus: EventBus, body: dict[str, Any]
    ) -> HandlingResult:
        return cls._publish_job_type(event_bus, super()._handle_body(event_bus, body))
