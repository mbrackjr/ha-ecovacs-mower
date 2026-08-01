"""Knappar: livslängdsåterställning och ljudsignal."""

from tests import requires_ha

pytestmark = requires_ha


def test_four_lifespan_reset_buttons() -> None:
    from custom_components.ecovacs_mower.button import LIFESPAN_ENTITY_DESCRIPTIONS

    assert {d.key for d in LIFESPAN_ENTITY_DESCRIPTIONS} == {
        "reset_lifespan_blade",
        "reset_lifespan_lens_brush",
        "reset_lifespan_trimmer_brush",
        "reset_lifespan_weed_rope",
    }


def test_play_sound_button_exists() -> None:
    """Kapabiliteten finns på 2i0fns men core exponerar den inte."""
    from custom_components.ecovacs_mower.button import ENTITY_DESCRIPTIONS

    assert {d.key for d in ENTITY_DESCRIPTIONS} == {"play_sound"}


def test_no_station_buttons() -> None:
    from custom_components.ecovacs_mower import button

    assert not hasattr(button, "STATION_ENTITY_DESCRIPTIONS")
    assert not hasattr(button, "EcovacsStationActionButtonEntity")


def test_every_description_has_a_translation() -> None:
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.button import (
        ENTITY_DESCRIPTIONS,
        LIFESPAN_ENTITY_DESCRIPTIONS,
    )

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    names = strings["entity"]["button"]

    for description in (*ENTITY_DESCRIPTIONS, *LIFESPAN_ENTITY_DESCRIPTIONS):
        assert description.translation_key in names, description.key


def test_every_button_has_an_icon() -> None:
    """En knapp utan egen ikon får HA:s generiska ikon — lätt att missa."""
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.button import (
        ENTITY_DESCRIPTIONS,
        LIFESPAN_ENTITY_DESCRIPTIONS,
    )

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    icons = json.loads((root / "icons.json").read_text(encoding="utf-8"))
    names = icons["entity"]["button"]

    for description in (*ENTITY_DESCRIPTIONS, *LIFESPAN_ENTITY_DESCRIPTIONS):
        assert description.translation_key in names, description.key
