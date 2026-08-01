"""Nummerentiteter: volym och klippriktning."""

from tests import requires_ha

pytestmark = requires_ha


def test_expected_number_keys() -> None:
    from custom_components.ecovacs_mower.number import ENTITY_DESCRIPTIONS

    assert {d.key for d in ENTITY_DESCRIPTIONS} == {"volume", "cut_direction"}


def test_cut_direction_is_a_line_orientation() -> None:
    """0-180 grader, inte 0-359.

    Klippriktningen är en linjeorientering, inte en kompassbäring: 180 grader
    täcker alla möjliga ränder, eftersom 190 och 10 ger samma mönster.
    Verifierat mot HA 2026.7.4.
    """
    from custom_components.ecovacs_mower.number import ENTITY_DESCRIPTIONS

    cut_direction = next(d for d in ENTITY_DESCRIPTIONS if d.key == "cut_direction")
    assert cut_direction.native_min_value == 0
    assert cut_direction.native_max_value == 180


def test_every_description_has_a_translation() -> None:
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.number import ENTITY_DESCRIPTIONS

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    names = strings["entity"]["number"]

    for description in ENTITY_DESCRIPTIONS:
        assert description.translation_key in names, description.key


def test_every_number_has_an_icon() -> None:
    """En number utan egen ikon får HA:s generiska slider — lätt att missa."""
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.number import ENTITY_DESCRIPTIONS

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    icons = json.loads((root / "icons.json").read_text(encoding="utf-8"))
    names = icons["entity"]["number"]

    for description in ENTITY_DESCRIPTIONS:
        assert description.translation_key in names, description.key


def test_no_stale_number_translations_or_icons() -> None:
    """Varje nyckel i strings.json/icons.json ska höra till en riktig number.

    Motsatsen till testerna ovan: de kollar beskrivning → sträng/ikon, inte
    tvärtom. Utan detta skulle en kvarglömd nyckel för en borttagen number
    gå obemärkt förbi.
    """
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.number import ENTITY_DESCRIPTIONS

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    icons = json.loads((root / "icons.json").read_text(encoding="utf-8"))

    keys = {d.translation_key for d in ENTITY_DESCRIPTIONS}
    assert set(strings["entity"]["number"]) <= keys
    assert set(icons["entity"]["number"]) <= keys
