"""Tests for mower area parameter and name parsing."""

from unittest.mock import Mock, call

from deebot_client.message import HandlingState

from custom_components.ecovacs_mower.deebot_patch.areas import (
    GetAreaParameter,
    GetAreaSet,
    MowerArea,
    MowerAreaNameEvent,
    MowerAreaParameterEvent,
    decode_cut_angle,
    decode_cut_speed,
    decode_mow_height,
    decode_obstacle_height,
    reset,
)


def setup_function() -> None:
    """Reset per-event-bus area state between tests."""
    reset()


def test_get_area_parameter_has_no_arguments() -> None:
    assert GetAreaParameter()._args == {}


def test_get_area_parameter_uses_the_expected_command_name() -> None:
    assert GetAreaParameter.NAME == "getAreaParameter"


def test_get_area_parameter_publishes_all_verified_fields() -> None:
    event_bus = Mock()
    result = GetAreaParameter()._handle_response(
        event_bus,
        {"ret": "ok", "resp": {"body": {"data": {"areaParameters": [{"areaID": 3, "mowHeightLevel": 4, "cutMode": 6, "obstacleHeight": 2, "angle": 90}]}}}},
    )

    assert result.state is HandlingState.SUCCESS
    assert event_bus.notify.call_args_list == [
        call(MowerAreaParameterEvent(areas=(MowerArea(area_id="3", mow_height_level=4, cut_mode=6, obstacle_height=2, angle=90),)))
    ]


def test_get_area_parameter_preserves_a_previously_read_name() -> None:
    event_bus = Mock()
    GetAreaParameter()._handle_response(
        event_bus,
        {"ret": "ok", "resp": {"body": {"data": {"areaParameters": [{"areaID": 3, "mowHeightLevel": 4}]}}}},
    )
    event_bus.reset_mock()

    area_set = GetAreaSet()
    area_set._buffer.add = Mock(return_value=b'[["map", "3", "Front lawn", [], [], [], 0]]')
    area_set._handle_response(
        event_bus,
        {"ret": "ok", "resp": {"body": {"data": {"subsets": "ignored"}}}},
    )
    event_bus.reset_mock()

    GetAreaParameter()._handle_response(
        event_bus,
        {"ret": "ok", "resp": {"body": {"data": {"areaParameters": [{"areaID": 3, "mowHeightLevel": 5}]}}}},
    )

    event = event_bus.notify.call_args.args[0]
    assert event.areas[0].name == "Front lawn"


def test_get_area_set_publishes_user_defined_names() -> None:
    event_bus = Mock()
    command = GetAreaSet()
    command._buffer.add = Mock(return_value=b'[["123", "7", "Front lawn", [], [100, 200], [300, 400], 0]]')

    result = command._handle_response(
        event_bus,
        {"ret": "ok", "resp": {"body": {"data": {"subsets": "ignored"}}}},
    )

    assert result.state is HandlingState.SUCCESS
    assert event_bus.notify.call_args_list == [
        call(MowerAreaNameEvent(names=(("7", "Front lawn"),)))
    ]


def test_get_area_set_ignores_malformed_rows() -> None:
    event_bus = Mock()
    command = GetAreaSet()
    command._buffer.add = Mock(return_value=b'[["123"], "not-a-row"]')

    result = command._handle_response(
        event_bus,
        {"ret": "ok", "resp": {"body": {"data": {"subsets": "ignored"}}}},
    )

    assert result.state is HandlingState.SUCCESS
    event_bus.notify.assert_not_called()


def test_get_area_set_decodes_a1600_friendly_names() -> None:
    event_bus = Mock()
    command = GetAreaSet()
    command._handle_response(
        event_bus,
        {
            "ret": "ok",
            "resp": {
                "body": {
                    "data": {
                        "subsets": "XQAABADEAAAAAC2WwEIAXhRj1JRBvSkBj/qBdAqB2QX0SG8/Vr8oDwPJ5NhnNLN8YjP8Zc0eJW+vO0bzfPWbfdtdB6JF19pttHbyaY0KU4cvE6HhcDC51FGUUnht81uyBrRaVIOJj7USxtAfp/hSzRTfkf6A",
                        "infoSize": 498,
                    }
                }
            },
        },
    )

    event = event_bus.notify.call_args.args[0]
    assert isinstance(event, MowerAreaNameEvent)
    assert dict(event.names) == {
        "1": "Achtertuin",
        "3": "Zijtuin",
        "2": "Voortuin",
        "4": "Laadstation",
    }


def test_a1600_mow_height_calibration() -> None:
    assert [decode_mow_height(level) for level in range(1, 8)] == [9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0]
    assert decode_mow_height(0) is None
    assert decode_mow_height(8) is None


def test_a1600_cut_speed_calibration() -> None:
    assert [decode_cut_speed(level) for level in range(1, 8)] == [0.70, 0.65, 0.60, 0.55, 0.50, 0.45, 0.40]
    assert decode_cut_speed(0) is None
    assert decode_cut_speed(8) is None


def test_a1600_obstacle_height_calibration() -> None:
    assert [decode_obstacle_height(level) for level in range(1, 4)] == [10, 15, 20]
    assert decode_obstacle_height(0) is None
    assert decode_obstacle_height(4) is None


def test_a1600_cut_angle_conversion_is_symmetric() -> None:
    for app_angle in (0, 1, 90, 180, 269, 270, 359):
        wire_angle = decode_cut_angle(app_angle)
        assert wire_angle is not None
        assert decode_cut_angle(wire_angle) == app_angle


def test_get_area_set_uses_the_expected_command_name() -> None:
    assert GetAreaSet.NAME == "getAreaSet"
