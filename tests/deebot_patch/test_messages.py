"""Tester för de meddelandehandlare biblioteket saknar."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from deebot_client.events import StateEvent
from deebot_client.models import State

from custom_components.ecovacs_mower.deebot_patch.messages import (
    OnChargeInfo,
    OnScheduleTaskInfo,
)


def _wrap(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "header": {
            "pri": 1,
            "tzm": 120,
            "ts": "1782211283816888165",
            "ver": "0.0.1",
            "fwVer": "1.9.16",
            "hwVer": "0.1.1",
        },
        "body": {"data": data},
    }


def _notified_states(message, data: dict[str, Any]) -> list[State]:
    """Kör handlern och returnera de tillstånd som notifierades."""
    event_bus = Mock()
    message.handle(event_bus, _wrap(data))
    return [
        call.args[0].state
        for call in event_bus.notify.call_args_list
        if isinstance(call.args[0], StateEvent)
    ]


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("goCharging", State.RETURNING),
        ("idle", State.DOCKED),
    ],
)
def test_on_charge_info(state: str, expected: State) -> None:
    # GOAT rapporterar återgång till dockan via onChargeInfo: "goCharging" på
    # väg hem, "idle" när jobbet är klart och den står i dockan.
    data = {"cid": "122", "trigger": "app", "state": state, "other": "0"}
    assert _notified_states(OnChargeInfo, data) == [expected]


@pytest.mark.parametrize("state", ["clean", "unknownState", ""])
def test_on_charge_info_ignores_other_states(state: str) -> None:
    data = {"cid": "122", "trigger": "app", "state": state}
    assert _notified_states(OnChargeInfo, data) == []


def test_on_charge_info_alert_overrides_docked_state() -> None:
    # "idle" betyder normalt DOCKED, men trigger="alert" är ett feltillstånd
    # och måste vinna även om state annars skulle tolkas som en lyckad dockning.
    data = {"cid": "122", "trigger": "alert", "state": "idle"}
    assert _notified_states(OnChargeInfo, data) == [State.ERROR]


def test_on_charge_info_alert_overrides_ignored_state() -> None:
    # Samma kontroll måste även slå igenom för ett state som annars ignoreras.
    data = {"cid": "122", "trigger": "alert", "state": "unknownState"}
    assert _notified_states(OnChargeInfo, data) == [State.ERROR]


@pytest.mark.parametrize(
    ("state", "clean_state", "expected"),
    [
        ("clean", {"motionState": "working"}, State.CLEANING),
        ("clean", {"motionState": "pause"}, State.PAUSED),
        ("clean", {"motionState": "goCharging"}, State.RETURNING),
        ("goCharging", None, State.RETURNING),
        ("idle", None, State.IDLE),
    ],
)
def test_on_schedule_task_info(
    state: str, clean_state: dict[str, Any] | None, expected: State
) -> None:
    # Schemalagda pass rapporteras via onScheduleTaskInfo med samma nyttolast
    # som onCleanInfo.
    data: dict[str, Any] = {"trigger": "continue", "other": "0", "state": state}
    if clean_state is not None:
        data["cleanState"] = clean_state
    assert _notified_states(OnScheduleTaskInfo, data) == [expected]


def test_on_schedule_task_info_alert_maps_to_error() -> None:
    data = {"trigger": "alert", "state": "clean"}
    assert _notified_states(OnScheduleTaskInfo, data) == [State.ERROR]


@pytest.mark.parametrize("state", ["unknownState", ""])
def test_on_schedule_task_info_ignores_other_states(state: str) -> None:
    data = {"trigger": "continue", "state": state}
    assert _notified_states(OnScheduleTaskInfo, data) == []


def test_message_names() -> None:
    # Namnen är nycklarna i bibliotekets register och måste stämma exakt.
    assert OnChargeInfo.NAME == "onChargeInfo"
    assert OnScheduleTaskInfo.NAME == "onScheduleTaskInfo"
