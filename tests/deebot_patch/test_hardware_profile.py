"""Tests for model-specific capability profiles."""

from custom_components.ecovacs_mower.deebot_patch.hardware import (
    SUPPORTED_CLASSES,
    profile_for_class,
)


def test_supported_classes_are_capability_profiles() -> None:
    """The supported-device registry carries capability metadata per class."""
    assert set(SUPPORTED_CLASSES) == {
        "2i0fns",
        "9bts2s",
        "2px96q",
        "77atlz",
        "e4gqia",
        "xmp9ds",
    }
    assert all(
        profile.device_class == class_
        for class_, profile in SUPPORTED_CLASSES.items()
    )


def test_area_parameter_protocol_is_enabled_only_for_explicit_classes() -> None:
    """Area protocol reads are opt-in per supported mower class."""
    assert profile_for_class("e4gqia") is not None
    assert profile_for_class("e4gqia").area_parameters is True

    for class_ in SUPPORTED_CLASSES:
        if class_ != "e4gqia":
            assert profile_for_class(class_).area_parameters is False
