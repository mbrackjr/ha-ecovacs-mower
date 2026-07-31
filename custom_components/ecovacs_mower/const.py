"""Konstanter för Ecovacs Mower."""

from enum import StrEnum

from deebot_client.events import LifeSpan

DOMAIN = "ecovacs_mower"

CONF_OVERRIDE_REST_URL = "override_rest_url"
CONF_OVERRIDE_MQTT_URL = "override_mqtt_url"
CONF_VERIFICATION_CODE = "verification_code"
CONF_VERIFY_MQTT_CERTIFICATE = "verify_mqtt_certificate"

# Endast de livslängdskomponenter en gräsklippare faktiskt har.
SUPPORTED_LIFESPANS = (
    LifeSpan.BLADE,
    LifeSpan.LENS_BRUSH,
    LifeSpan.TRIMMER_BRUSH,
    LifeSpan.WEED_ROPE,
)


class InstanceMode(StrEnum):
    """Installationsläge."""

    CLOUD = "cloud"
    SELF_HOSTED = "self_hosted"
