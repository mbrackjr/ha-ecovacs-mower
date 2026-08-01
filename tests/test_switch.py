"""Switcharna ska motsvara inställningarna en GOAT har."""

from tests import requires_ha

pytestmark = requires_ha


def test_expected_switch_keys() -> None:
    """Låser uppsättningen. Ändras den ska det vara ett beslut, inte ett olycksfall."""
    from custom_components.ecovacs_mower.switch import ENTITY_DESCRIPTIONS

    assert {d.key for d in ENTITY_DESCRIPTIONS} == {
        "advanced_mode",
        "true_detect",
        "border_switch",
        "child_lock",
        "move_up_warning",
        "cross_map_border_warning",
        "safe_protect",
    }


def test_no_vacuum_only_switches() -> None:
    """Kapabiliteterna finns inte på 2i0fns, så entiteterna vore ändå tomma."""
    from custom_components.ecovacs_mower.switch import ENTITY_DESCRIPTIONS

    keys = {d.key for d in ENTITY_DESCRIPTIONS}
    assert keys.isdisjoint(
        {"continuous_cleaning", "carpet_auto_fan_boost", "clean_preference", "border_spin"}
    )


def test_every_description_has_a_translation() -> None:
    """En saknad nyckel ger råa strängar i gränssnittet."""
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.switch import ENTITY_DESCRIPTIONS

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    names = strings["entity"]["switch"]

    for description in ENTITY_DESCRIPTIONS:
        assert description.translation_key in names, description.key
