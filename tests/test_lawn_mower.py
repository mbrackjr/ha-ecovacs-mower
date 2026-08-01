"""Tillståndskartan och styrkommandona.

Modulen under test importerar Home Assistant, som inte går att importera på
Windows (``fcntl``). Importerna ligger därför inne i testfunktionerna och hela
filen är märkt ``requires_ha`` — annars kraschar redan insamlingen, innan någon
skip-markör hinner gälla. Sanningskällan är CI på ubuntu-latest.
"""

import pytest

from . import requires_ha

pytestmark = requires_ha


@pytest.mark.parametrize(
    ("state_name", "expected_name"),
    [
        ("CLEANING", "MOWING"),
        ("PAUSED", "PAUSED"),
        ("RETURNING", "RETURNING"),
        ("DOCKED", "DOCKED"),
        ("ERROR", "ERROR"),
    ],
)
def test_state_mapping(state_name: str, expected_name: str) -> None:
    from deebot_client.models import State
    from homeassistant.components.lawn_mower import LawnMowerActivity

    from custom_components.ecovacs_mower.lawn_mower import _STATE_TO_MOWER_STATE

    state = getattr(State, state_name)
    expected = getattr(LawnMowerActivity, expected_name)
    assert _STATE_TO_MOWER_STATE[state] == expected


def test_idle_maps_to_paused_not_docked() -> None:
    # En klippare som står stilla mitt på gräsmattan är pausad, inte dockad.
    from deebot_client.models import State
    from homeassistant.components.lawn_mower import LawnMowerActivity

    from custom_components.ecovacs_mower.lawn_mower import _STATE_TO_MOWER_STATE

    assert _STATE_TO_MOWER_STATE[State.IDLE] == LawnMowerActivity.PAUSED


def test_every_state_is_mapped() -> None:
    # Ohanterat tillstånd ger KeyError i callbacken och tyst trasig entitet.
    from deebot_client.models import State

    from custom_components.ecovacs_mower.lawn_mower import _STATE_TO_MOWER_STATE

    assert set(_STATE_TO_MOWER_STATE) == set(State)


def test_supported_features() -> None:
    # LawnMowerEntity använder HA:s CachedProperties-metaklass för
    # "supported_features", som skriver om klassattributet
    # ``_attr_supported_features`` till en property. Läst på klassen (utan
    # instans) ger det property-objektet självt, inte flaggvärdet — därför
    # läses det via en instans, precis som HA gör vid körning.
    # ``__new__`` kringgår ``__init__`` (som kräver en riktig ``Device``)
    # eftersom descriptorn inte beror på att den kört.
    from homeassistant.components.lawn_mower import LawnMowerEntityFeature

    from custom_components.ecovacs_mower.lawn_mower import EcovacsMower

    instance = EcovacsMower.__new__(EcovacsMower)
    assert instance._attr_supported_features == (
        LawnMowerEntityFeature.DOCK
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.START_MOWING
    )
