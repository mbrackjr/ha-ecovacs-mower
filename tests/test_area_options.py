"""Zone names in the mow_area action's area picker.

The module under test imports Home Assistant, which cannot be imported on
Windows (fcntl). Imports live inside the tests and the file is marked
requires_ha. The source of truth is CI on ubuntu-latest.
"""

from unittest.mock import MagicMock, patch

from . import requires_ha

pytestmark = requires_ha


def _mower(did: str, area: object, nick: str = "GOAT") -> MagicMock:
    """A device whose subscriptions are captured rather than run."""
    device = MagicMock()
    device.device_info = {"did": did, "class": "e4gqia", "nick": nick}
    device.capabilities.clean.action.area = area
    return device


def _entry() -> MagicMock:
    """A config entry that collects its unload callbacks."""
    entry = MagicMock()
    entry.unloads = []
    entry.async_on_unload.side_effect = entry.unloads.append
    return entry


def _areas(*zones: tuple[str, str | None]):
    from custom_components.ecovacs_mower.deebot_patch.areas import (
        MowerArea,
        MowerAreaEvent,
    )

    return MowerAreaEvent(
        tuple(MowerArea(area_id, name=name) for area_id, name in zones)
    )


def _on_areas(device: MagicMock):
    """The MowerAreaEvent callback the device was subscribed with."""
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerAreaEvent

    event_type, callback = device.events.subscribe.call_args.args
    assert event_type is MowerAreaEvent
    return callback


def test_zones_are_labelled_by_name_and_valued_by_id() -> None:
    from custom_components.ecovacs_mower.area_options import zone_options

    options = zone_options(
        {"did": ("GOAT", {"7": None, "10": "Back", "3": "Front"})}
    )

    # Ordered by ID as a number, not as a string; an unnamed zone by its ID.
    assert options == [
        {"label": "Front", "value": "3"},
        {"label": "Area 7", "value": "7"},
        {"label": "Back", "value": "10"},
    ]


def test_two_mowers_prefix_their_names() -> None:
    from custom_components.ecovacs_mower.area_options import zone_options

    options = zone_options(
        {
            "did-b": ("Rear", {"1": "Lawn"}),
            "did-a": ("Front", {"1": "Lawn"}),
            # Reports no zones, so it does not count as a second mower.
            "did-c": ("Other", {}),
        }
    )

    assert options == [
        {"label": "Front · Lawn", "value": "1"},
        {"label": "Rear · Lawn", "value": "1"},
    ]


def test_duplicate_names_carry_their_id() -> None:
    from custom_components.ecovacs_mower.area_options import zone_options

    options = zone_options({"did": ("GOAT", {"1": "Lawn", "2": "Lawn", "3": "Edge"})})

    assert [option["label"] for option in options] == [
        "Lawn (1)",
        "Lawn (2)",
        "Edge",
    ]


def test_ids_the_action_would_reject_are_not_offered() -> None:
    from custom_components.ecovacs_mower.area_options import zone_options

    options = zone_options({"did": ("GOAT", {"1": "A", "1000": "B", "x1": "C"})})

    assert [option["value"] for option in options] == ["1"]


async def test_zone_names_replace_the_text_field(hass) -> None:
    from homeassistant.helpers.service import async_get_all_descriptions

    from custom_components.ecovacs_mower import async_setup
    from custom_components.ecovacs_mower.area_options import (
        async_setup_zone_options,
    )
    from custom_components.ecovacs_mower.deebot_patch.zonal import MowArea

    assert await async_setup(hass, {})
    device = _mower("did", MowArea)
    entry = _entry()
    await async_setup_zone_options(hass, entry, [device])

    await _on_areas(device)(_areas(("1", "Front lawn"), ("3", None)))

    description = (await async_get_all_descriptions(hass))["ecovacs_mower"][
        "mow_area"
    ]
    # Everything but the selector comes from services.yaml, target included.
    assert description["target"] == {
        "entity": {"domain": "lawn_mower", "integration": "ecovacs_mower"}
    }
    field = description["fields"]["area_ids"]
    assert field["required"] is True
    assert field["selector"] == {
        "select": {
            "multiple": True,
            "custom_value": True,
            "options": [
                {"label": "Front lawn", "value": "1"},
                {"label": "Area 3", "value": "3"},
            ],
        }
    }

    # Unloading the last mower puts the static field from services.yaml back.
    for unload in entry.unloads:
        unload()
    description = (await async_get_all_descriptions(hass))["ecovacs_mower"][
        "mow_area"
    ]
    assert description["fields"]["area_ids"]["selector"] == {
        "text": {"multiple": True, "type": "number"}
    }


async def test_unchanged_zones_are_not_published_again(hass) -> None:
    from custom_components.ecovacs_mower.area_options import (
        async_setup_zone_options,
    )
    from custom_components.ecovacs_mower.deebot_patch.zonal import MowArea

    device = _mower("did", MowArea)
    await async_setup_zone_options(hass, _entry(), [device])

    with patch(
        "custom_components.ecovacs_mower.area_options.async_set_service_schema"
    ) as publish:
        # A parameter-only push is a MowerAreaEvent too, and changes no zone.
        await _on_areas(device)(_areas(("1", "Front lawn")))
        await _on_areas(device)(_areas(("1", "Front lawn")))
        assert publish.call_count == 1

        await _on_areas(device)(_areas(("1", "Voortuin")))
        assert publish.call_count == 2


async def test_mowers_without_zone_mowing_are_not_followed(hass) -> None:
    from custom_components.ecovacs_mower.area_options import (
        async_setup_zone_options,
    )

    device = _mower("did", None)
    await async_setup_zone_options(hass, _entry(), [device])

    device.events.subscribe.assert_not_called()
