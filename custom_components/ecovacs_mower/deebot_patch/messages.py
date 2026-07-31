"""Meddelandehandlare som deebot-client saknar för gräsklippare.

Motsvarar DeebotUniverse/client.py PR #1647. GOAT rapporterar sitt tillstånd
via tre oombedda MQTT-meddelanden, men biblioteket hanterar bara ett av dem:

    onCleanInfo         manuell start/paus      hanteras av biblioteket
    onScheduleTaskInfo  schemalagt pass         faller igenom som okänt
    onChargeInfo        hemfärd / klart         faller igenom som okänt

Utan de två sistnämnda lämnar entiteten aldrig "docked" under ett schemalagt
pass, och återgår aldrig till "returning"/"docked" efter avslutat arbete.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from deebot_client.events import StateEvent
from deebot_client.logging_filter import get_logger
from deebot_client.message import HandlingResult, MessageBodyDataDict
from deebot_client.models import State

if TYPE_CHECKING:
    from deebot_client.event_bus import EventBus

_LOGGER = get_logger(__name__)


def handle_clean_info(event_bus: EventBus, data: dict[str, Any]) -> HandlingResult:
    """Tolka en clean-info-nyttolast och notifiera motsvarande tillstånd.

    Delas av ``onScheduleTaskInfo`` och ``onCleanInfo``, som har identisk
    nyttolast: ``{"state": "clean", "cleanState": {"motionState": "working"}}``.

    Tillståndet härleds ur ``state`` — vad enheten gör — inte ur ``trigger``,
    som bara anger vem som begärde åtgärden.
    """
    status: State | None = None
    state = data.get("state")
    if data.get("trigger") == "alert":
        status = State.ERROR
    # "washing" är mopptvätt och kan aldrig förekomma på en gräsklippare.
    # Den behålls ändå: grenen är kopierad ordagrant från bibliotekets egen
    # clean-info-parsning, och en identisk kopia är lättare att jämföra mot
    # uppströms den dag PR #1647 mergas och det här kan raderas.
    elif state in ("clean", "washing"):
        clean_state = data.get("cleanState", {})
        motion_state = clean_state.get("motionState")
        if motion_state == "working":
            status = State.CLEANING
        elif motion_state == "pause":
            status = State.PAUSED
        elif motion_state == "goCharging":
            status = State.RETURNING
    elif state == "goCharging":
        status = State.RETURNING
    elif state == "idle":
        status = State.IDLE

    if status is not None:
        event_bus.notify(StateEvent(status))
        return HandlingResult.success()

    return HandlingResult.analyse()


class OnChargeInfo(MessageBodyDataDict):
    """Hemfärd och dockning."""

    NAME = "onChargeInfo"

    @classmethod
    def _handle_body_data_dict(
        cls, event_bus: EventBus, data: dict[str, Any]
    ) -> HandlingResult:
        """Hantera message->body->data.

        Till skillnad från clean-info ligger tillståndet här på toppnivå:
        "goCharging" på väg hem, "idle" när arbetet är klart.
        """
        match data.get("state"):
            case "goCharging":
                status = State.RETURNING
            case "idle":
                status = State.DOCKED
            case _:
                return HandlingResult.analyse()

        event_bus.notify(StateEvent(status))
        return HandlingResult.success()


class OnScheduleTaskInfo(MessageBodyDataDict):
    """Schemalagt klippass."""

    NAME = "onScheduleTaskInfo"

    @classmethod
    def _handle_body_data_dict(
        cls, event_bus: EventBus, data: dict[str, Any]
    ) -> HandlingResult:
        """Hantera message->body->data."""
        return handle_clean_info(event_bus, data)
