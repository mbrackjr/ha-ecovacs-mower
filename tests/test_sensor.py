"""Sensoruppsättningen ska spegla vad en GOAT faktiskt har."""

from tests import requires_ha

pytestmark = requires_ha


def test_no_station_sensor() -> None:
    """station_state beskriver en dammsugarstations tömningspåse."""
    from custom_components.ecovacs_mower.sensor import ENTITY_DESCRIPTIONS

    assert not any(d.key == "station_state" for d in ENTITY_DESCRIPTIONS)


def test_no_legacy_classes() -> None:
    from custom_components.ecovacs_mower import sensor

    assert not hasattr(sensor, "EcovacsLegacyBatterySensor")
    assert not hasattr(sensor, "EcovacsLegacyLifespanSensor")
    assert not hasattr(sensor, "LEGACY_LIFESPAN_SENSORS")


def test_expected_sensor_keys() -> None:
    """Låser uppsättningen. Ändras den ska det vara ett beslut, inte ett olycksfall.

    ``error`` lever inte i ``ENTITY_DESCRIPTIONS``: precis som i core har
    ``EcovacsErrorSensor`` sin ``entity_description`` som klassattribut och
    byggs separat i ``async_setup_entry``, inte via ``get_supported_entities``.
    Att lägga in den i ``ENTITY_DESCRIPTIONS`` hade fått get_supported_entities
    att bygga en andra, generisk ``EcovacsSensor`` med samma unique_id
    (``{did}_error``) som den riktiga ``EcovacsErrorSensor`` — en krock i
    entity-registret. Testet slår därför ihop de två källorna till en mängd.
    """
    from homeassistant.const import ATTR_BATTERY_LEVEL

    from custom_components.ecovacs_mower.sensor import (
        ENTITY_DESCRIPTIONS,
        EcovacsErrorSensor,
    )

    keys = {d.key for d in ENTITY_DESCRIPTIONS} | {
        EcovacsErrorSensor.entity_description.key
    }
    assert keys == {
        "stats_area",
        "stats_time",
        "total_stats_area",
        "total_stats_time",
        "total_stats_cleanings",
        ATTR_BATTERY_LEVEL,
        "network_ip",
        "network_rssi",
        "network_ssid",
        "error",
    }


def test_four_lifespan_sensors() -> None:
    from custom_components.ecovacs_mower.sensor import LIFESPAN_ENTITY_DESCRIPTIONS

    assert {d.key for d in LIFESPAN_ENTITY_DESCRIPTIONS} == {
        "lifespan_blade",
        "lifespan_lens_brush",
        "lifespan_trimmer_brush",
        "lifespan_weed_rope",
    }


def test_every_description_has_a_translation() -> None:
    """En saknad nyckel ger råa strängar i gränssnittet.

    Inkluderar även ``EcovacsErrorSensor``, som har sin egen
    ``entity_description`` utanför ``ENTITY_DESCRIPTIONS`` (se
    ``test_expected_sensor_keys``).
    """
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.sensor import (
        ENTITY_DESCRIPTIONS,
        LIFESPAN_ENTITY_DESCRIPTIONS,
        EcovacsErrorSensor,
    )

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    names = strings["entity"]["sensor"]

    descriptions = (
        *ENTITY_DESCRIPTIONS,
        *LIFESPAN_ENTITY_DESCRIPTIONS,
        EcovacsErrorSensor.entity_description,
    )
    for description in descriptions:
        if description.translation_key:
            assert description.translation_key in names, description.key


def test_every_sensor_has_an_icon() -> None:
    """En sensor utan egen ikon får HA:s generiska ikon — lätt att missa.

    Sensor var den första plattformen och skapade ``icons.json``; mönstret
    med ett ikontest per plattform uppfanns en task senare och har aldrig
    eftermonterats här förrän nu. Inkluderar ``EcovacsErrorSensor`` av samma
    skäl som ``test_every_description_has_a_translation``.
    """
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.sensor import (
        ENTITY_DESCRIPTIONS,
        LIFESPAN_ENTITY_DESCRIPTIONS,
        EcovacsErrorSensor,
    )

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    icons = json.loads((root / "icons.json").read_text(encoding="utf-8"))
    names = icons["entity"]["sensor"]

    descriptions = (
        *ENTITY_DESCRIPTIONS,
        *LIFESPAN_ENTITY_DESCRIPTIONS,
        EcovacsErrorSensor.entity_description,
    )
    for description in descriptions:
        if description.translation_key:
            assert description.translation_key in names, description.key


def test_no_stale_sensor_translations_or_icons() -> None:
    """Varje nyckel i strings.json/icons.json ska höra till en riktig sensor.

    Motsatsen till testerna ovan: de kollar beskrivning → sträng/ikon, inte
    tvärtom. Utan detta skulle en kvarglömd nyckel för en borttagen sensor
    gå obemärkt förbi.
    """
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.sensor import (
        ENTITY_DESCRIPTIONS,
        LIFESPAN_ENTITY_DESCRIPTIONS,
        EcovacsErrorSensor,
    )

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    icons = json.loads((root / "icons.json").read_text(encoding="utf-8"))

    descriptions = (
        *ENTITY_DESCRIPTIONS,
        *LIFESPAN_ENTITY_DESCRIPTIONS,
        EcovacsErrorSensor.entity_description,
    )
    keys = {d.translation_key for d in descriptions if d.translation_key}

    assert set(strings["entity"]["sensor"]) <= keys
    assert set(icons["entity"]["sensor"]) <= keys
