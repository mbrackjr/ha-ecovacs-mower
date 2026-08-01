"""Tester för get_client_device_id — den bärande egenskapen i 1013-fixen.

Ecovacs kräver e-postverifiering av klientens enhets-ID (felkod 1013) om
inte samma ID återanvänds vid varje inloggning. Genererades ett nytt ID
varje gång skulle användaren hamna i en oändlig verifieringsloop utan att
förstå varför. Dessa tester bevisar direkt att ett redan känt ID i
konfigurationen alltid vinner över att generera ett nytt, och att ett nytt
ID bara genereras när inget finns sedan tidigare.

``util.py`` importerar bara ``homeassistant.core``/``const``/``util``, inte
``homeassistant.runner`` (som gör det oskyddade ``import fcntl`` som annars
kraschar insamling på Windows). Modulen går därför att importera direkt här
utan pytest-homeassistant-custom-component-pluginet, och testerna behöver
ingen ``hass``-fixture — de kan köras på riktigt lokalt, inte bara samlas
in som skippade.
"""

import string

from homeassistant.const import CONF_DEVICE_ID

from custom_components.ecovacs_mower.util import get_client_device_id

_DEVICE_ID_ALPHABET = set(string.ascii_uppercase + string.digits)


def test_existing_device_id_is_reused() -> None:
    """Kärnan i 1013-fixen: ett känt ID återanvänds, aldrig omgenererat."""
    config = {CONF_DEVICE_ID: "ALREADY-VERIFIED-ID"}

    assert get_client_device_id(None, False, config) == "ALREADY-VERIFIED-ID"
    # Gäller oavsett installationsläge — reauth mot en self-hosted-entry
    # får inte heller trigga en ny verifieringsrunda.
    assert get_client_device_id(None, True, config) == "ALREADY-VERIFIED-ID"


def test_missing_device_id_is_generated() -> None:
    """Utan ett tidigare ID genereras ett nytt, slumpmässigt ID."""
    device_id = get_client_device_id(None, False, {})

    assert device_id
    assert len(device_id) == 8
    assert set(device_id) <= _DEVICE_ID_ALPHABET


def test_supported_lifespans_are_the_four_a_mower_has() -> None:
    """Endast de komponenter 2i0fns faktiskt deklarerar.

    Core exponerar 12 av ``LifeSpan``-enumens 26 medlemmar, samtliga
    dammsugarinriktade. BLADE och LENS_BRUSH ingår i den listan; TRIMMER_BRUSH
    och WEED_ROPE gör det inte alls — de är gräsklipparspecifika komponenter
    core aldrig exponerar.
    """
    from deebot_client.events import LifeSpan

    from custom_components.ecovacs_mower.const import SUPPORTED_LIFESPANS

    assert set(SUPPORTED_LIFESPANS) == {
        LifeSpan.BLADE,
        LifeSpan.LENS_BRUSH,
        LifeSpan.TRIMMER_BRUSH,
        LifeSpan.WEED_ROPE,
    }


def test_supported_lifespans_match_the_target_device() -> None:
    """Vår lista får inte innehålla något enheten saknar."""
    import asyncio

    from deebot_client.hardware import _DEVICES, get_static_device_info

    from custom_components.ecovacs_mower.const import SUPPORTED_LIFESPANS

    # get_static_device_info seedar den globala cachen. Repokonventionen är att
    # lämna den som vi fann den — se tests/deebot_patch/test_hardware.py.
    try:
        info = asyncio.run(get_static_device_info("2i0fns"))
        assert info is not None
        assert set(SUPPORTED_LIFESPANS) <= set(info.capabilities.life_span.types)
    finally:
        _DEVICES.pop("2i0fns", None)
