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


def test_redact_covers_the_fork_specific_leaks() -> None:
    """Tre nycklar uppströms aldrig behövde maskera.

    * ``CONF_DEVICE_ID``: kärnan persisterar aldrig klientens enhets-ID —
      den genererar ett nytt vid varje start, vilket *är* 1013-buggen.
      Vi sparar det i ``entry.data``, så det når dumpen. Self-hosted är
      värdet ``HA-{slugify(location_name)}`` (hemnamnet, PII); i molnläge
      är det den verifierade klientidentiteten, som ihop med ett läckt
      konto hoppar över e-postverifieringen.
    * ``nick``/``resource``: står i ``ApiDeviceInfo`` och följer med rakt
      in i dumpen, eftersom ``device.device_info`` *är* den råa api-dicten.
      ``resource`` är andra halvan av MQTT-topicen.
    """
    from homeassistant.const import CONF_DEVICE_ID

    from custom_components.ecovacs_mower.diagnostics import REDACT

    assert {CONF_DEVICE_ID, "nick", "resource"} <= REDACT


def test_device_info_keys_are_covered_or_deliberately_public() -> None:
    """Varje nyckel i ApiDeviceInfo ska vara ett medvetet beslut.

    ``device.device_info`` returnerar api-dicten oavkortat. Lägger
    uppströms till en nyckel ska den här raden bli röd, så att någon
    faktiskt tar ställning i stället för att låta den läcka ut i en
    diagnostikrapport som klistras in i ett GitHub-ärende.
    """
    from deebot_client.models import ApiDeviceInfo

    from custom_components.ecovacs_mower.diagnostics import REDACT

    # Medvetet omaskerade: modellklass och tillverkare är inte identifierande
    # och är precis det man behöver för att felsöka ett ärende.
    public = {"class", "company", "deviceName"}

    assert set(ApiDeviceInfo.__annotations__) <= REDACT | public
