"""Ecovacs util functions.

Forkad från Home Assistant core (``homeassistant/components/ecovacs/util.py``).
``get_name_key`` och ``get_options`` är fortfarande borttagna — de används bara
av select-plattformen, som denna integration inte har. ``get_supported_entities``
är återställd i fas 2: sensor-, switch-, number- och buttonplattformarna
använder den för att bygga sina entiteter ur ``EcovacsCapabilityEntityDescription``.
"""

from collections.abc import Mapping
import random
import string
from typing import TYPE_CHECKING, Any, cast

from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .entity import (
    EcovacsCapabilityEntityDescription,
    EcovacsDescriptionEntity,
    EcovacsEntity,
)

if TYPE_CHECKING:
    from .controller import EcovacsController


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


def get_supported_entities(
    controller: "EcovacsController",
    entity_class: type[EcovacsDescriptionEntity],
    descriptions: tuple[EcovacsCapabilityEntityDescription, ...],
) -> list[EcovacsEntity]:
    """Return all supported entities for all devices."""
    return [
        entity_class(device, capability, description)
        for device in controller.devices
        for description in descriptions
        if (capability := description.capability_fn(device.capabilities))
    ]
