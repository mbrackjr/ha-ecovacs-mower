"""REDACT måste maskera allt uppströms kärna maskerar.

Modulen under test importerar Home Assistant (via ``diagnostics.py``, som i
sin tur importerar paketets ``__init__``), som inte går att importera på
Windows (``fcntl``). Importerna ligger därför inne i testfunktionerna och
hela filen är märkt ``requires_ha`` — annars kraschar redan insamlingen,
innan någon skip-markör hinner gälla. Sanningskällan är CI på ubuntu-latest.
"""

from . import requires_ha

pytestmark = requires_ha


def test_redact_covers_everything_core_redacts() -> None:
    """Kontraktet, inte en engångsobservation.

    homeassistant/components/ecovacs/diagnostics.py maskerar
    CONF_USERNAME, CONF_PASSWORD, "title", CONF_OVERRIDE_MQTT_URL,
    CONF_OVERRIDE_REST_URL (config) samt "did", CONF_NAME, "homeId"
    (enhet). "title" behövs inte här — vi dumpar entry.data, inte
    entry.as_dict() — men resten ska finnas, annars läcker en
    diagnostikrapport uppgifter en användare delar offentligt.
    """
    from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME

    from custom_components.ecovacs_mower.const import (
        CONF_OVERRIDE_MQTT_URL,
        CONF_OVERRIDE_REST_URL,
    )
    from custom_components.ecovacs_mower.diagnostics import REDACT

    must_redact = {
        CONF_USERNAME,
        CONF_PASSWORD,
        CONF_OVERRIDE_MQTT_URL,
        CONF_OVERRIDE_REST_URL,
        "did",
        CONF_NAME,
        "homeId",
    }
    assert must_redact <= REDACT
