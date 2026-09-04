"""Tests for dynamic mower area sensors."""

from tests import requires_ha

pytestmark = requires_ha


def test_area_sensor_descriptions_have_stable_ids_and_icons() -> None:
    """Area IDs form the unique keys while every sensor has an explicit icon."""
    from custom_components.ecovacs_mower.area_sensors import area_sensor_descriptions

    descriptions = area_sensor_descriptions("2")

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
    from custom_components.ecovacs_mower.area_sensors import area_sensor_descriptions

    assert all(
        description.name != "Area name"
        for description in area_sensor_descriptions("2")
    )


def test_area_sensor_uses_fixed_parameter_names() -> None:
    """Parameter labels are deliberately fixed English integration names."""
    from custom_components.ecovacs_mower.area_sensors import area_sensor_descriptions

    assert [description.name for description in area_sensor_descriptions("2")] == [
        "Cutting height",
        "Mowing speed",
        "Obstacle height",
        "Cutting direction",
    ]
