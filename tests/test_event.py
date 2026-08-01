"""Senaste jobbet som händelseentitet."""

from tests import requires_ha

pytestmark = requires_ha


def test_last_job_entity_exists() -> None:
    from custom_components.ecovacs_mower.event import EcovacsLastJobEventEntity

    assert EcovacsLastJobEventEntity.entity_description.key == "stats_report"


def test_event_types_cover_the_report_states() -> None:
    """Ett rapporterat tillstånd utanför listan tappas av HA."""
    from custom_components.ecovacs_mower.event import EcovacsLastJobEventEntity

    types = EcovacsLastJobEventEntity.entity_description.event_types
    assert types, "event_types får inte vara tom"


def test_event_types_match_get_name_key_of_the_reportable_statuses() -> None:
    """event_types låses mot de CleanJobStatus-värden entiteten faktiskt triggar på.

    NO_STATUS och CLEANING filtreras bort i on_event — bara avslutade jobb
    ska nå _trigger_event, så bara de tre återstående statusarna hör hemma här.
    """
    from deebot_client.events import CleanJobStatus

    from custom_components.ecovacs_mower.event import EcovacsLastJobEventEntity
    from custom_components.ecovacs_mower.util import get_name_key

    reportable = {
        status
        for status in CleanJobStatus
        if status not in (CleanJobStatus.NO_STATUS, CleanJobStatus.CLEANING)
    }

    assert set(EcovacsLastJobEventEntity.entity_description.event_types) == {
        get_name_key(status) for status in reportable
    }


def test_translation_exists() -> None:
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.event import EcovacsLastJobEventEntity

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    key = EcovacsLastJobEventEntity.entity_description.translation_key
    assert key in strings["entity"]["event"]


def test_translated_states_cover_every_event_type() -> None:
    """Ett tillstånd utan översättning visar en rå sträng i gränssnittet."""
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.event import EcovacsLastJobEventEntity

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    key = EcovacsLastJobEventEntity.entity_description.translation_key
    states = strings["entity"]["event"][key]["state_attributes"]["event_type"]["state"]

    for event_type in EcovacsLastJobEventEntity.entity_description.event_types:
        assert event_type in states, event_type


def test_last_job_entity_has_an_icon() -> None:
    """En händelseentitet utan egen ikon får HA:s generiska ikon."""
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.event import EcovacsLastJobEventEntity

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    icons = json.loads((root / "icons.json").read_text(encoding="utf-8"))
    key = EcovacsLastJobEventEntity.entity_description.translation_key
    assert key in icons["entity"]["event"]


def test_no_stale_event_translations_or_icons() -> None:
    """Varje nyckel i strings.json/icons.json ska höra till en riktig händelse.

    Motsatsen till testerna ovan: de kollar beskrivning → sträng/ikon, inte
    tvärtom. Utan detta skulle en kvarglömd nyckel för en borttagen
    händelseentitet gå obemärkt förbi.
    """
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.event import EcovacsLastJobEventEntity

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    icons = json.loads((root / "icons.json").read_text(encoding="utf-8"))
    key = EcovacsLastJobEventEntity.entity_description.translation_key

    assert set(strings["entity"]["event"]) <= {key}
    assert set(icons["entity"]["event"]) <= {key}
