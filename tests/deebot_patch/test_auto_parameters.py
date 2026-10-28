"""The mower-wide settings, read as the ``auto`` area.

The followed app writes are driven through the library's own
``MqttClient._handle_p2p``, so what is tested is what the MQTT client really
does with the registered commands. Topics and payloads are the A1600 RTK's
from issue #23.
"""

from types import SimpleNamespace
from unittest.mock import Mock

from deebot_client.commands import COMMANDS_WITH_MQTT_P2P_HANDLING
from deebot_client.commands.json.border_switch import SetBorderSwitch
from deebot_client.const import DataType
from deebot_client.events import CutDirectionEvent
from deebot_client.message import HandlingState
from deebot_client.mqtt_client import MqttClient
import pytest

from custom_components.ecovacs_mower.deebot_patch import apply
from custom_components.ecovacs_mower.deebot_patch.areas import (
    AREA_PARAMETER_KEYS,
    AUTO_AREA_ID,
    MowerAutoEvent,
    auto_for,
)
from custom_components.ecovacs_mower.deebot_patch.commands import (
    AUTO_READ_COMMANDS,
    AUTO_WRITE_COMMANDS,
    GetCutEfficiency,
    GetCutHeight,
    GetMowerCutDirection,
    GetObstacleHeight,
    SetCutEfficiency,
    SetCutHeight,
    SetMowerCutDirection,
    SetObstacleHeight,
)

_APP = "HelperMQClientId-sts-ngiot-mqserver-eco1-34/ecosys/1234"
_MOWER = "did/xmp9ds/res"
_OK = (
    b'{"header":{"tzm":180,"ts":"1792573628910452821","fwVer":"1.17.11"},'
    b'"body":{"code":0,"msg":"ok"}}'
)
_REFUSED = b'{"header":{"fwVer":"1.17.11"},"body":{"code":3,"msg":"fail"}}'


def _set(data: str) -> bytes:
    return (
        b'{"body":{"data":' + data.encode() + b'},"header":{"channel":"Android",'
        b'"m":"request","pri":2,"reqid":"eabfme","ts":"1792573628262","ver":"0.0.22"}}'
    )


def _client(events: Mock) -> SimpleNamespace:
    """What _handle_p2p reads from the client: its pending requests and subscriptions."""
    return SimpleNamespace(
        _received_p2p_commands={},
        _subscriptions={"did": SimpleNamespace(events=events)},
    )


def _exchange(client, command: str, request: bytes, answer: bytes) -> None:
    topic = f"iot/p2p/{command}/{_APP}/{_MOWER}/q/b33n/j".split("/")
    MqttClient._handle_p2p(client, topic, request)
    topic = f"iot/p2p/{command}/{_MOWER}/{_APP}/p/b33n/j".split("/")
    MqttClient._handle_p2p(client, topic, answer)


def _auto_events(events: Mock) -> list[MowerAutoEvent]:
    return [
        call.args[0]
        for call in events.notify.call_args_list
        if isinstance(call.args[0], MowerAutoEvent)
    ]


def test_the_commands_cover_the_area_keys_in_order() -> None:
    assert [cmd.NAME for cmd in AUTO_READ_COMMANDS] == [
        "getCutHeight",
        "getCutEfficiency",
        "getObstacleHeight",
        "getCutDirection",
    ]
    assert [cmd.NAME for cmd in AUTO_WRITE_COMMANDS] == [
        "setCutHeight",
        "setCutEfficiency",
        "setObstacleHeight",
        "setCutDirection",
    ]
    assert [cmd.get_command for cmd in AUTO_WRITE_COMMANDS] == list(
        AUTO_READ_COMMANDS
    )
    assert [cmd.PARAMETER_KEY for cmd in AUTO_READ_COMMANDS[:3]] == list(
        AREA_PARAMETER_KEYS[:3]
    )


@pytest.mark.parametrize(
    ("command", "data", "key", "value"),
    [
        (GetCutHeight, {"level": 6}, "mowHeightLevel", 6),
        (GetCutEfficiency, {"level": 2}, "cutMode", 2),
        (GetObstacleHeight, {"level": 3}, "obstacleHeight", 3),
        (GetMowerCutDirection, {"angle": 179}, "angle", 179),
    ],
)
def test_an_answer_is_kept_under_the_area_key(command, data, key, value) -> None:
    events = Mock()

    result = command.handle_set_args(events, data)

    assert result.state is HandlingState.SUCCESS
    assert auto_for(events).area_id == AUTO_AREA_ID
    assert dict(auto_for(events).parameters) == {key: value}
    [event] = _auto_events(events)
    assert event.area == auto_for(events)


def test_answers_are_merged_per_key() -> None:
    events = Mock()

    GetCutHeight.handle_set_args(events, {"level": 6})
    GetCutEfficiency.handle_set_args(events, {"level": 1})
    GetCutHeight.handle_set_args(events, {"level": 5})

    assert dict(auto_for(events).parameters) == {"mowHeightLevel": 5, "cutMode": 1}


@pytest.mark.parametrize("data", [{}, {"level": "6"}, {"level": True}, {"lvl": 6}])
def test_an_unusable_answer_is_not_kept(data) -> None:
    events = Mock()

    result = GetCutHeight.handle_set_args(events, data)

    assert result.state is HandlingState.ANALYSE
    assert dict(auto_for(events).parameters) == {}
    events.notify.assert_not_called()


def test_the_cut_direction_answer_still_feeds_the_librarys_event() -> None:
    # The device-wide cutting direction number reads CutDirectionEvent.
    events = Mock()

    GetMowerCutDirection.handle_set_args(events, {"angle": 270})

    published = [call.args[0] for call in events.notify.call_args_list]
    assert CutDirectionEvent(angle=270) in published
    assert dict(auto_for(events).parameters) == {"angle": 270}


def test_apply_registers_the_writes_and_keeps_the_librarys_entries() -> None:
    apply()
    apply()
    table = COMMANDS_WITH_MQTT_P2P_HANDLING[DataType.JSON]

    assert table["setCutHeight"] is SetCutHeight
    assert table["setCutEfficiency"] is SetCutEfficiency
    assert table["setObstacleHeight"] is SetObstacleHeight
    assert table["setCutDirection"] is SetMowerCutDirection
    assert table["setBorderSwitch"] is SetBorderSwitch


@pytest.mark.parametrize(
    ("command", "data", "key", "value"),
    [
        ("setCutHeight", '{"level":7}', "mowHeightLevel", 7),
        ("setCutEfficiency", '{"level":2}', "cutMode", 2),
        ("setObstacleHeight", '{"level":3}', "obstacleHeight", 3),
        ("setCutDirection", '{"angle":90}', "angle", 90),
    ],
)
def test_an_accepted_app_write_is_followed(command, data, key, value) -> None:
    apply()
    events = Mock()

    _exchange(_client(events), command, _set(data), _OK)

    assert dict(auto_for(events).parameters) == {key: value}


def test_a_refused_app_write_is_not_followed() -> None:
    apply()
    events = Mock()

    _exchange(_client(events), "setCutHeight", _set('{"level":7}'), _REFUSED)

    assert dict(auto_for(events).parameters) == {}
