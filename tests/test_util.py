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
