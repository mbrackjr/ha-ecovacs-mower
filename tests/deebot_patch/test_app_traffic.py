"""The app's requests to the mower and its answers, observed during a capture.

Driven through the library's own ``MqttClient._handle_p2p``, so what is
tested is what the MQTT client really does with the wrapped table, not a
copy of it. The topics and payloads are the A1600 RTK's from issue #23.
"""

from types import SimpleNamespace
from unittest.mock import Mock

from deebot_client.commands import COMMANDS_WITH_MQTT_P2P_HANDLING
from deebot_client.commands.json.border_switch import SetBorderSwitch
from deebot_client.const import DataType
from deebot_client.events import BorderSwitchEvent
from deebot_client.mqtt_client import MqttClient

from custom_components.ecovacs_mower.deebot_patch import apply
from custom_components.ecovacs_mower.deebot_patch.app_traffic import (
    MowerAppTrafficEvent,
    ObservingTable,
    capture,
)

_APP = "HelperMQClientId-sts-ngiot-mqserver-eco1-34/ecosys/1234"
_MOWER = "did/xmp9ds/res"


def _request(command: str, request_id: str = "b33n") -> list[str]:
    return f"iot/p2p/{command}/{_APP}/{_MOWER}/q/{request_id}/j".split("/")


def _answer(command: str, request_id: str = "b33n") -> list[str]:
    return f"iot/p2p/{command}/{_MOWER}/{_APP}/p/{request_id}/j".split("/")


def _client(events: Mock) -> SimpleNamespace:
    """What _handle_p2p reads from the client: its pending requests and subscriptions."""
    return SimpleNamespace(
        _received_p2p_commands={},
        _subscriptions={"did": SimpleNamespace(events=events)},
    )


def _exchange(client, command: str, request: bytes, answer: bytes) -> None:
    MqttClient._handle_p2p(client, _request(command), request)
    MqttClient._handle_p2p(client, _answer(command), answer)


def _traffic(events: Mock) -> list[MowerAppTrafficEvent]:
    return [
        call.args[0]
        for call in events.notify.call_args_list
        if isinstance(call.args[0], MowerAppTrafficEvent)
    ]


_SET_CUT_HEIGHT = (
    b'{"body":{"data":{"level":7}},"header":{"channel":"Android","m":"request",'
    b'"pri":2,"reqid":"eabfme","ts":"1792573628262","ver":"0.0.22"}}'
)
_OK = b'{"header":{"tzm":180,"ts":"1792573628910452821","fwVer":"1.17.11"},"body":{"code":0,"msg":"ok"}}'


def test_apply_wraps_the_table_the_mqtt_client_reads_and_is_idempotent() -> None:
    apply()
    table = COMMANDS_WITH_MQTT_P2P_HANDLING[DataType.JSON]
    apply()

    assert isinstance(table, ObservingTable)
    assert COMMANDS_WITH_MQTT_P2P_HANDLING[DataType.JSON] is table
    # The library's own entries are all still there, unchanged.
    assert table["setBorderSwitch"] is SetBorderSwitch


def test_without_a_capture_the_table_answers_as_the_librarys_own() -> None:
    apply()
    table = COMMANDS_WITH_MQTT_P2P_HANDLING[DataType.JSON]

    assert table.get("setBorderSwitch") is SetBorderSwitch
    assert table.get("setCutHeight") is None


def test_without_a_capture_an_unknown_request_is_dropped_as_before() -> None:
    apply()
    events = Mock()
    client = _client(events)

    _exchange(client, "setCutHeight", _SET_CUT_HEIGHT, _OK)

    assert client._received_p2p_commands == {}
    events.notify.assert_not_called()


def test_a_command_the_library_does_not_know_is_reported() -> None:
    apply()
    events = Mock()
    stop = capture()

    _exchange(_client(events), "setCutHeight", _SET_CUT_HEIGHT, _OK)
    stop()

    [event] = _traffic(events)
    assert (
        event.command,
        event.request,
        event.response,
        event.code,
        event.channel,
    ) == (
        "setCutHeight",
        '{"level":7}',
        None,
        0,
        "Android",
    )


def test_a_read_reports_the_data_the_mower_answered() -> None:
    apply()
    events = Mock()
    stop = capture()

    _exchange(
        _client(events),
        "getBorderSwitch",
        b'{"body":{"data":{}},"header":{"channel":"iOS"}}',
        b'{"header":{},"body":{"code":0,"msg":"ok","data":{"enable":1,"mode":2}}}',
    )
    stop()

    [event] = _traffic(events)
    assert (event.request, event.response, event.channel) == (
        "{}",
        '{"enable":1,"mode":2}',
        "iOS",
    )


def test_a_command_the_library_knows_keeps_its_own_handling() -> None:
    # setBorderSwitch is in the library's table: its BorderSwitchEvent, which
    # the Edge cutting switch follows, must still be published. The app also
    # sends a mode, which the library ignores and the capture shows.
    apply()
    events = Mock()
    stop = capture()

    _exchange(
        _client(events),
        "setBorderSwitch",
        b'{"body":{"data":{"enable":1,"mode":2}},"header":{"channel":"Android"}}',
        _OK,
    )
    stop()

    published = [call.args[0] for call in events.notify.call_args_list]
    assert BorderSwitchEvent(True) in published
    [event] = _traffic(events)
    assert (event.command, event.request) == (
        "setBorderSwitch",
        '{"enable":1,"mode":2}',
    )


def test_a_refusal_carries_its_code() -> None:
    apply()
    events = Mock()
    stop = capture()

    _exchange(
        _client(events),
        "setCutHeight",
        _SET_CUT_HEIGHT,
        b'{"header":{},"body":{"code":30005,"msg":"fail"}}',
    )
    stop()

    [event] = _traffic(events)
    assert event.code == 30005


def test_a_request_without_json_is_still_reported_without_failing() -> None:
    apply()
    events = Mock()
    stop = capture()

    _exchange(_client(events), "setCutHeight", b"not json", b"not json either")
    stop()

    [event] = _traffic(events)
    assert (event.request, event.response, event.code, event.channel) == (
        "{}",
        None,
        None,
        None,
    )


def test_observing_stops_when_the_last_capture_ends() -> None:
    apply()
    table = COMMANDS_WITH_MQTT_P2P_HANDLING[DataType.JSON]
    first, second = capture(), capture()

    first()
    first()  # a second call changes nothing
    assert table.get("setCutHeight") is not None
    second()
    assert table.get("setCutHeight") is None
