"""Tests for dynamic mower area parameter entities."""

from tests import requires_ha

pytestmark = requires_ha


def _descriptions():
    """Return A1600 descriptions using the HA-only model mapping."""
    from custom_components.ecovacs_mower.area_sensors import (
        AREA_PARAMETER_MAPPINGS,
        area_sensor_descriptions,
    )

    return area_sensor_descriptions(
        "2", area_mapping=AREA_PARAMETER_MAPPINGS["e4gqia"]
    )


def test_area_sensor_descriptions_have_stable_ids_and_icons() -> None:
    """Area IDs form the unique keys while every entity has an explicit icon."""
    descriptions = _descriptions()

    assert [description.key for description in descriptions] == [
        "area_2_cutting_height",
        "area_2_mowing_speed",
        "area_2_obstacle_height",
        "area_2_cut_direction",
    ]
    assert [description.suggested_object_id for description in descriptions] == [
        "2_cutting_height",
        "2_mowing_speed",
        "2_obstacle_height",
        "2_cut_direction",
    ]
    assert [description.icon for description in descriptions] == [
        "mdi:grass",
        "mdi:speedometer",
        "mdi:format-vertical-align-top",
        "mdi:angle-acute",
    ]
    assert [description.name for description in descriptions] == [
        "Cutting height",
        "Mowing speed",
        "Obstacle height",
        "Cutting direction",
    ]
    assert all(description.translation_key is None for description in descriptions)
    assert [description.raw_field for description in descriptions] == [
        "mow_height_level",
        "cut_mode",
        "obstacle_height",
        "angle",
    ]


def test_area_sensor_descriptions_do_not_include_a_name_sensor() -> None:
    """The mower name is part of each parameter entity's integration name."""
    assert all(description.name != "Area name" for description in _descriptions())


def test_area_sensor_uses_fixed_parameter_names() -> None:
    """Parameter labels are deliberately fixed English integration names."""
    assert [description.name for description in _descriptions()] == [
        "Cutting height",
        "Mowing speed",
        "Obstacle height",
        "Cutting direction",
    ]


def test_a1600_representation_mapping_is_ha_owned() -> None:
    """A1600 raw-value interpretation is defined by the HA layer."""
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerArea

    descriptions = _descriptions()
    assert descriptions[0].value_fn(
        MowerArea(area_id="2", mow_height_level=1)
    ) == 9


def test_a1600_lookup_mapping_derives_number_metadata() -> None:
    """Lookup values provide conversion and the HA number range/step metadata."""
    descriptions = _descriptions()

    assert (descriptions[0].native_min_value, descriptions[0].native_max_value, descriptions[0].native_step) == (3.0, 9.0, 1.0)
    assert (descriptions[1].native_min_value, descriptions[1].native_max_value, descriptions[1].native_step) == (0.40, 0.70, 0.05)
    assert (descriptions[2].native_min_value, descriptions[2].native_max_value, descriptions[2].native_step) == (10.0, 20.0, 5.0)
    assert (descriptions[3].native_min_value, descriptions[3].native_max_value, descriptions[3].native_step) == (0, 359, 1)


def test_area_parameter_lookup_round_trips_and_derives_raw_range() -> None:
    """A lookup reverses the same validated table for writable values."""
    from custom_components.ecovacs_mower.area_sensors import (
        AREA_PARAMETER_MAPPINGS,
    )

    mapping = AREA_PARAMETER_MAPPINGS["e4gqia"]

    assert mapping.mow_height.raw_start == 1
    assert mapping.mow_height.raw_end == 7
    assert [mapping.mow_height.to_native(raw) for raw in range(1, 8)] == [
        9, 8, 7, 6, 5, 4, 3
    ]
    assert [mapping.mow_height.to_raw(value) for value in range(3, 10)] == [
        7, 6, 5, 4, 3, 2, 1
    ]
    assert mapping.mow_height.to_native(0) is None
    assert mapping.mow_height.to_native(8) is None
    assert mapping.mow_height.to_raw(2) is None
    assert mapping.mow_height.to_raw(10) is None


def test_a1600_mow_height_calibration() -> None:
    """A1600 mow-height levels map to the observed centimetre values."""
    description = _descriptions()[0]
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerArea

    assert [
        description.value_fn(MowerArea(area_id="2", mow_height_level=level))
        for level in range(1, 8)
    ] == [9, 8, 7, 6, 5, 4, 3]
    assert description.value_fn(MowerArea(area_id="2", mow_height_level=0)) is None
    assert description.value_fn(MowerArea(area_id="2", mow_height_level=8)) is None
    assert [description.to_raw_fn(value) for value in range(3, 10)] == [7, 6, 5, 4, 3, 2, 1]
    assert description.to_raw_fn(2) is None
    assert description.to_raw_fn(10) is None


def test_a1600_cut_speed_calibration() -> None:
    """A1600 cut-mode levels map to the observed metres-per-second values."""
    description = _descriptions()[1]
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerArea

    assert [
        description.value_fn(MowerArea(area_id="2", cut_mode=level))
        for level in range(1, 8)
    ] == [0.70, 0.65, 0.60, 0.55, 0.50, 0.45, 0.40]
    assert description.value_fn(MowerArea(area_id="2", cut_mode=0)) is None
    assert description.value_fn(MowerArea(area_id="2", cut_mode=8)) is None
    assert [description.to_raw_fn(value) for value in (0.70, 0.65, 0.60, 0.55, 0.50, 0.45, 0.40)] == [1, 2, 3, 4, 5, 6, 7]
    assert description.to_raw_fn(0.35) is None
    assert description.to_raw_fn(0.675) is None


def test_a1600_obstacle_height_calibration() -> None:
    """A1600 obstacle-height levels map to the observed centimetre values."""
    description = _descriptions()[2]
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerArea

    assert [
        description.value_fn(MowerArea(area_id="2", obstacle_height=level))
        for level in range(1, 4)
    ] == [10, 15, 20]
    assert description.value_fn(MowerArea(area_id="2", obstacle_height=0)) is None
    assert description.value_fn(MowerArea(area_id="2", obstacle_height=4)) is None
    assert [description.to_raw_fn(value) for value in (10, 15, 20)] == [1, 2, 3]
    assert description.to_raw_fn(5) is None
    assert description.to_raw_fn(10.5) is None


def test_a1600_cut_angle_conversion_is_symmetric() -> None:
    """A1600 wire-space and HA-space angle conversion is symmetric."""
    description = _descriptions()[3]
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerArea

    for app_angle in (0, 1, 90, 180, 269, 270, 359):
        wire_angle = description.value_fn(
            MowerArea(area_id="2", angle=app_angle)
        )
        assert wire_angle is not None
        assert description.to_raw_fn(wire_angle) == app_angle

    assert description.to_raw_fn(-1) is None
    assert description.to_raw_fn(360) is None


def test_area_write_merges_one_changed_raw_field() -> None:
    """One writable view changes only its field in the complete raw command."""
    from custom_components.ecovacs_mower.area_sensors import build_set_area_parameter
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerArea

    command = build_set_area_parameter(
        MowerArea(
            area_id="2",
            mow_height_level=4,
            cut_mode=6,
            obstacle_height=2,
            angle=90,
        ),
        "mow_height_level",
        7,
    )

    assert command is not None
    assert command._args == {
        "areaID": "2",
        "mowHeightLevel": 7,
        "cutMode": 6,
        "obstacleHeight": 2,
        "angle": 90,
    }


def test_area_write_refuses_incomplete_authoritative_state() -> None:
    """A write never invents a missing raw field."""
    from custom_components.ecovacs_mower.area_sensors import build_set_area_parameter
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerArea

    assert (
        build_set_area_parameter(
            MowerArea(area_id="2", mow_height_level=4, cut_mode=6),
            "mow_height_level",
            7,
        )
        is None
    )
