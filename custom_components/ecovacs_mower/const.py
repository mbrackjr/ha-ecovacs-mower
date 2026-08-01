"""Konstanter för Ecovacs Mower."""

from enum import StrEnum

from deebot_client.events import LifeSpan

DOMAIN = "ecovacs_mower"

# Speglar manifest.json:s issue_tracker. Används i loggmeddelanden, som inte
# kan läsa manifestet.
ISSUE_TRACKER_URL = "https://github.com/nord-/ha-ecovacs-mower/issues"

CONF_OVERRIDE_REST_URL = "override_rest_url"
CONF_OVERRIDE_MQTT_URL = "override_mqtt_url"
CONF_VERIFICATION_CODE = "verification_code"
CONF_VERIFY_MQTT_CERTIFICATE = "verify_mqtt_certificate"


class InstanceMode(StrEnum):
    """Installationsläge."""

    CLOUD = "cloud"
    SELF_HOSTED = "self_hosted"


# Endast de livslängdskomponenter en gräsklippare faktiskt har. Core listar 17;
# de övriga 13 är moppar, dammpåsar, filter och UV-lampor.
SUPPORTED_LIFESPANS = (
    LifeSpan.BLADE,
    LifeSpan.LENS_BRUSH,
    LifeSpan.TRIMMER_BRUSH,
    LifeSpan.WEED_ROPE,
)
