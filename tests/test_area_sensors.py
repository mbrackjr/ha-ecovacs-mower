"""Tests for dynamic mower area sensors."""

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
    """Area IDs form the unique keys while every sensor has an explicit icon."""
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


def test_area_sensor_descriptions_do_not_include_a_name_sensor() -> None:
    """The mower name is part of each parameter sensor's integration name."""
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
    ) == 9.0


def test_a1600_mow_height_calibration() -> None:
    """A1600 mow-height levels map to the observed centimetre values."""
    mapping = _descriptions()[0].value_fn
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerArea

    assert [mapping(MowerArea(area_id="2", mow_height_level=level)) for level in range(1, 8)] == [
        9.0,
        8.0,
        7.0,
        6.0,
        5.0,
        4.0,
        3.0,
    ]
    assert mapping(MowerArea(area_id="2", mow_height_level=0)) is None
    assert mapping(MowerArea(area_id="2", mow_height_level=8)) is None


def test_a1600_cut_speed_calibration() -> None:
    """A1600 cut-mode levels map to the observed metres-per-second values."""
    mapping = _descriptions()[1].value_fn
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerArea

    assert [mapping(MowerArea(area_id="2", cut_mode=level)) for level in range(1, 8)] == [
        0.70,
        0.65,
        0.60,
        0.55,
        0.50,
        0.45,
        0.40,
    ]
    assert mapping(MowerArea(area_id="2", cut_mode=0)) is None
    assert mapping(MowerArea(area_id="2", cut_mode=8)) is None


def test_a1600_obstacle_height_calibration() -> None:
    """A1600 obstacle-height levels map to the observed centimetre values."""
    mapping = _descriptions()[2].value_fn
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerArea

    assert [mapping(MowerArea(area_id="2", obstacle_height=level)) for level in range(1, 4)] == [
        10,
        15,
        20,
    ]
    assert mapping(MowerArea(area_id="2", obstacle_height=0)) is None
    assert mapping(MowerArea(area_id="2", obstacle_height=4)) is None


def test_a1600_cut_angle_conversion_is_symmetric() -> None:
    """A1600 wire-space and HA-space angle conversion is symmetric."""
    mapping = _descriptions()[3].value_fn
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerArea

    for app_angle in (0, 1, 90, 180, 269, 270, 359):
        wire_angle = mapping(MowerArea(area_id="2", angle=app_angle))
        assert wire_angle is not None
        assert mapping(MowerArea(area_id="2", angle=wire_angle)) == app_angle
