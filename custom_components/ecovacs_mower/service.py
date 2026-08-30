"""Services for Ecovacs GOAT mowers."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

SERVICE_MOW_AREA = "mow_area"
SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("area_ids"): vol.All(cv.ensure_list, [vol.Coerce(int)]),
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_service(hass: HomeAssistant) -> None:
    """Register the zone-mowing service."""
    if hass.services.has_service(DOMAIN, SERVICE_MOW_AREA):
        return

    async def _mow_area(call: ServiceCall) -> None:
        device_ids = call.data.get(ATTR_DEVICE_ID, [])
        if len(device_ids) != 1:
            raise HomeAssistantError("mow_area requires exactly one mower device")

        registry_device = dr.async_get(hass).async_get(device_ids[0])
        if registry_device is None:
            raise HomeAssistantError("Mower device was not found")

        entry_id = next(iter(registry_device.config_entries), None)
        if entry_id is None:
            raise HomeAssistantError("Mower device has no config entry")
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            raise HomeAssistantError("Mower config entry was not found")

        did = next(
            (
                identifier[1]
                for identifier in registry_device.identifiers
                if identifier[0] == DOMAIN
            ),
            None,
        )
        device = next(
            (
                device
                for device in entry.runtime_data.devices
                if device.device_info["did"] == did
            ),
            None,
        )
        if device is None:
            raise HomeAssistantError("Mower device is not available")

        area = device.capabilities.clean.action.area
        if area is None:
            raise HomeAssistantError("This mower does not support zone mowing")

        await device.execute_command(area("spotArea", call.data["area_ids"], 1))

    hass.services.async_register(
        DOMAIN,
        SERVICE_MOW_AREA,
        _mow_area,
        schema=SERVICE_SCHEMA,
    )
