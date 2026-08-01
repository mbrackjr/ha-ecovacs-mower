"""Ecovacs util functions.

Forkad från Home Assistant core (``homeassistant/components/ecovacs/util.py``).
``get_name_key``, ``get_options`` och ``get_supported_entities`` är borttagna —
de används bara av select-, sensor- och switchplattformarna, som kommer i fas 2.

Att ``get_supported_entities`` är borta lämnar ``EcovacsDescriptionEntity`` och
``EcovacsCapabilityEntityDescription`` i ``entity.py`` utan anropare. De står
kvar med flit: de är forkade basklasser från kärnan som fas 2 behöver, och att
härleda dem igen är sämre än att bära dem.
"""

from collections.abc import Mapping
import random
import string
from typing import Any, cast

from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify


def get_client_device_id(
    hass: HomeAssistant, self_hosted: bool, config: Mapping[str, Any]
) -> str:
    """Get client device id."""
    if device_id := config.get(CONF_DEVICE_ID):
        return cast(str, device_id)
    if self_hosted:
        return f"HA-{slugify(hass.config.location_name)}"

    return "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(8)
    )
